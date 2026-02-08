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
        # 1. 讀取風控設定
        self.leverage = config.get("risk", "leverage", 1)
        
        # 2. 讀取資金分配設定
        self.default_amount = config.get("risk", "default_amount", 100)
        self.allocations = config.get("risk", "strategy_allocations", {})
        
        self.risk_manager = RiskManager(leverage=self.leverage)
        
        # 設定交易所槓桿 (只需設一次)
        if not self.is_paper:
            self.executor.set_leverage(self.symbol, self.leverage)
    
    def _get_strategy_amount(self, strategy_name):
        """ 取得該策略分配的金額 """
        return self.allocations.get(strategy_name, self.default_amount)

    def log_snapshot(self, current_price):
        """ 
        [修改] 這裡顯示的是「交易所總持倉」，但也要加上「策略持倉分布」
        """
        details = self.executor.get_position_details(self.symbol)
        total_amt = details['amt'] if details else 0.0
        
        logging.info(f"[SNAPSHOT] 交易所總持倉: {total_amt} BTC | 現價: {current_price}")
        return total_amt

    def process_signal(self, signal_data, current_pos_amt):
        """ 
        [核心修改] 
        不再看 current_pos_amt (總持倉)，
        而是去 DB 查這個策略自己有沒有持倉 
        """
        strategy_name = signal_data['strategy_name']
        action = signal_data['action']
        reason = signal_data['reason']
        ref_price = signal_data['ref_price']

        # 1. 查詢該策略目前的「虛擬持倉」
        strat_pos_qty, strat_entry_price = self.db.get_strategy_position(strategy_name, self.symbol)
        
        logging.info(f"[SIGNAL] {strategy_name} ({strat_pos_qty} BTC) | {action} | {reason}")
        self.db.log_signal(strategy_name, self.symbol, action, ref_price, reason)

        target_qty = 0
        should_trade = False

        if action == 'LONG':
            # 策略自己沒倉位才能開 (忽略別的策略有沒有單)
            if strat_pos_qty > 0:
                logging.info(f"[SKIP] {strategy_name} 已有持倉 {strat_pos_qty}，跳過開倉")
            else:
                # 取得該策略分配的金額
                amount = self._get_strategy_amount(strategy_name)
                # 計算下單量
                target_qty = self.risk_manager.calculate_quantity(ref_price, amount)
                should_trade = True
        
        elif action == 'CLOSE':
            # 策略自己有倉位才能平
            if strat_pos_qty > 0:
                # 平倉數量 = 該策略持有的數量 (確保一一對應)
                target_qty = strat_pos_qty
                should_trade = True
            else:
                logging.info(f"[SKIP] {strategy_name} 目前空手，無法平倉")
        
        # 執行交易
        if should_trade and target_qty > 0:
            self._execute_order(strategy_name, action, target_qty, ref_price)

    def _execute_order(self, strategy_name, action, quantity, market_price):
        """ 底層下單邏輯 (不變) """
        side = 'BUY' if action == 'LONG' else 'SELL'
        is_reduce = (action == 'CLOSE')
        
        # 這裡發送給幣安的是「淨操作」
        response = self.executor.execute_order(
            self.symbol, side, quantity, reduce_only=is_reduce, market_price=market_price
        )
        
        if not response: return

        order_id = response.get('orderId')
        logging.info(f"[{strategy_name}] 訂單已發送 ID: {order_id}")
        time.sleep(3) 

        # 查證訂單
        final_record = self._verify_order(order_id, response)
        
        if final_record and final_record['executedQty'] > 0:
            # 這裡 DB 寫入時已經有 strategy_name 了，所以紀錄是分開的
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