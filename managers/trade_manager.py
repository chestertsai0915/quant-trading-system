import logging
import time
from utils.notifier import send_tg_msg
from execution.risk_manager import RiskManager
from execution.binance_executor import BinanceExecutor
from execution.mock_executor import MockExecutor

class TradeManager:
    def __init__(self, client, db, config, symbol, is_paper=False):
        self.client = client
        self.db = db
        self.symbol = symbol
        self.is_paper = is_paper
        
        # 初始化執行器
        if self.is_paper:
            self.executor = MockExecutor()
        else:
            self.executor = BinanceExecutor(self.client)
            
        # 初始化風控
        leverage = config.get("risk", "leverage", 1)
        fixed_amount = config.get("risk", "fixed_amount", 20)
        self.risk_manager = RiskManager(fixed_usdt_amount=fixed_amount, leverage=leverage)
        
        # 設定槓桿
        if not self.is_paper:
            self.executor.set_leverage(self.symbol, leverage)

    def log_snapshot(self, current_price):
        """ 資產快照 """
        details = self.executor.get_position_details(self.symbol)
        amt = details['amt'] if details else 0.0
        
        if abs(amt) > 0:
            logging.info(f"[SNAPSHOT] 持倉: {amt} | PnL: {details['unRealizedProfit']} U")
        else:
            logging.info(f"[SNAPSHOT] 空手 | 現價: {current_price}")
        
        return amt

    def process_signal(self, signal_data, current_pos_amt):
        """ 處理單一策略訊號 """
        strategy_name = signal_data['strategy_name']
        action = signal_data['action']
        reason = signal_data['reason']
        ref_price = signal_data['ref_price']

        # 紀錄訊號到 DB
        logging.info(f"[SIGNAL] {strategy_name} | {action} | {reason}")
        self.db.log_signal(strategy_name, self.symbol, action, ref_price, reason)

        # 計算下單量
        target_qty = 0
        should_trade = False

        if action == 'LONG':
            if current_pos_amt > 0:
                logging.info(f"[SKIP] {strategy_name} 喊多但已有持倉")
            else:
                target_qty = self.risk_manager.calculate_quantity(ref_price)
                should_trade = True
        
        elif action == 'CLOSE':
            if current_pos_amt > 0:
                target_qty = abs(current_pos_amt)
                should_trade = True
        
        # 執行交易
        if should_trade and target_qty > 0:
            self._execute_order(strategy_name, action, target_qty, ref_price)

    def _execute_order(self, strategy_name, action, quantity, market_price):
        """ 底層下單邏輯 """
        side = 'BUY' if action == 'LONG' else 'SELL'
        is_reduce = (action == 'CLOSE')
        
        response = self.executor.execute_order(
            self.symbol, side, quantity, reduce_only=is_reduce, market_price=market_price
        )
        
        if not response: return

        order_id = response.get('orderId')
        logging.info(f"訂單已發送 ID: {order_id}，等待撮合...")
        time.sleep(3) # 等待成交

        # 查證訂單
        final_record = self._verify_order(order_id, response)
        
        if final_record and final_record['executedQty'] > 0:
            self._log_trade_success(strategy_name, action, final_record, order_id)
        else:
            logging.warning(f"訂單 {order_id} 未完全成交")

    def _verify_order(self, order_id, response):
        """ 查證訂單狀態 """
        if self.is_paper:
            return {
                'avgPrice': float(response.get('cumQuote', 0)) / float(response.get('executedQty', 1)),
                'executedQty': float(response.get('executedQty', 0)),
                'notional': float(response.get('cumQuote', 0))
            }
        return self.executor.fetch_order_status(self.symbol, order_id)

    def _log_trade_success(self, strategy_name, action, record, order_id):
        avg_price = record['avgPrice']
        qty = record['executedQty']
        
        # DB 紀錄
        self.db.log_trade(
            strategy=strategy_name, symbol=self.symbol, side=action,
            price=avg_price, quantity=qty, order_id=str(order_id),
            notional=record['notional']
        )
        
        # TG 通知
        send_tg_msg(f"[成交] {action} {self.symbol}\n策略: {strategy_name}\n數量: {qty}\n均價: {avg_price:.2f}")
        logging.info(f"[VERIFIED] 成交確認 | 均價: {avg_price}")