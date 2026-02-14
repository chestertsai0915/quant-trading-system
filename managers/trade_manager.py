import logging
import time
from utils.notifier import send_tg_msg
from execution.risk_manager import RiskManager
from execution.binance_executor import BinanceExecutor
from execution.mock_executor import MockExecutor
from .portfolio_manager import PortfolioManager 

class TradeManager:
    def __init__(self, client, db, config, symbol, is_paper=False):
        self.client = client
        self.db = db
        self.config = config
        self.symbol = symbol
        self.is_paper = is_paper
        
        if self.is_paper:
            self.executor = MockExecutor()
        else:
            self.executor = BinanceExecutor(self.client)
            
        self.risk_manager = RiskManager(leverage=config.get("risk", "leverage", 1))
        self.portfolio_manager = PortfolioManager(config, db) 
        
        if not self.is_paper:
            self.executor.set_leverage(self.symbol, config.get("risk", "leverage", 1))

    def update_virtual_signal(self, signal_data):
        """
        第一步：接收策略訊號，更新 DB 裡的虛擬持倉狀態
        """
        strategy_name = signal_data['strategy_name']
        action = signal_data['action']
        ref_price = signal_data['ref_price']
        reason = signal_data.get('reason', 'No Reason') # 取得原因
        # 1. Log 訊號細節 (應您的要求)
        logging.info(f"[SIGNAL] {strategy_name} ({ref_price}) | {action} | {reason}")
        # 解析訊號 (標準化)
        target_virtual_pos = 0.0
        if action == 'LONG': target_virtual_pos = 1.0
        elif action == 'SHORT': target_virtual_pos = -1.0
        # 3. 讀取當前虛擬持倉 (為了判斷 SKIP 邏輯)
        current_virtual_pos, _, _ = self.db.get_strategy_state(strategy_name)

        # 4. 判斷邏輯 (完全保留您的邏輯)
        # 這裡的 quantity 其實就是 position (1, -1, 0)
        if target_virtual_pos == current_virtual_pos:
            if current_virtual_pos == 0 and (action == 'CLOSE' or action == 'FLAT'):
                logging.info(f"[SKIP] {strategy_name} 目前空手，無法平倉/無需動作")
            elif current_virtual_pos != 0:
                logging.info(f"[SKIP] {strategy_name} 已有持倉 {current_virtual_pos}，部位無變化")
            else:
                logging.info(f"[SKIP] {strategy_name} 無需調倉")
            return
        
        # 更新虛擬帳本 (只寫 DB)
        self._update_virtual_state(strategy_name, target_virtual_pos, ref_price)

    #  [公開方法] 讓 Bot 在迴圈結束後呼叫一次
    def execute_global_rebalance(self, price):
        """
        第二步：計算全域目標部位，並執行差額交易
        Global Target = Total Equity * Sum(Weight * Virtual_Pos)
        """
        # 1. 取得帳戶資訊
        account_info = self.executor.get_account_info()
        total_equity = float(account_info['totalWalletBalance']) if account_info else 1000.0
        
        # 2. 取得所有成分
        weights = self.portfolio_manager.get_all_weights(total_equity, price)
        virtual_positions = self.db.get_all_virtual_positions()
        
        # 3. 計算總曝險比例
        net_exposure_ratio = 0.0
        for strat, weight in weights.items():
            pos = virtual_positions.get(strat, 0.0)
            net_exposure_ratio += weight * pos
            
        # 4. 計算目標持倉
        leverage = self.config.get("risk", "leverage", 1)
        target_value = total_equity * net_exposure_ratio * leverage
        target_qty = target_value / price
        
        # 5. 取得目前真實持倉
        current_real_qty = self.executor.get_current_position(self.symbol)
        
        # 6. 計算差額
        delta_qty = target_qty - current_real_qty
        
        # 7. 門檻過濾 (10U)
        MIN_TRADE_VALUE = 10.0
        delta_value = abs(delta_qty * price)
        
        logging.info(f"[Global] 權益:{total_equity:.0f} | 曝險:{net_exposure_ratio:.2%} | 目標:{target_qty:.4f} | 現有:{current_real_qty:.4f}")

        # 如果目標是 0 (完全平倉)，必須執行
        if abs(target_qty) < 1e-6 and abs(current_real_qty) > 1e-6:
             pass 
        elif delta_value < MIN_TRADE_VALUE:
             return # 變動太小，跳過

        # 8. 執行下單
        side = 'BUY' if delta_qty > 0 else 'SELL'
        qty_abs = abs(delta_qty)
        
        if qty_abs > 0:
            logging.info(f"[EXEC] 差額調倉: {side} {qty_abs:.4f}")
            self.executor.execute_order(self.symbol, side, qty_abs, market_price=price)
            
            msg = f"[Net Rebalance] 曝險調整: {net_exposure_ratio:.1%}\n動作: {side} {qty_abs:.4f}\n價格: {price}"
            send_tg_msg(msg)

    def _update_virtual_state(self, strategy_name, target_pos, price):
        
        current_pos, entry_price, _ = self.db.get_strategy_state(strategy_name)
        if current_pos == target_pos: return

        VIRTUAL_CAPITAL = 1000.0 
        pnl = 0.0
        if current_pos != 0:
            pct_change = (price - entry_price) / entry_price if entry_price > 0 else 0
            direction = 1 if current_pos > 0 else -1
            pnl = pct_change * direction * VIRTUAL_CAPITAL
            import time
            self.db.log_trade(
                strategy=strategy_name, symbol=self.symbol, side='CLOSE' if target_pos == 0 else 'REVERSE',
                price=price, quantity=0, order_id=f"virt_{int(time.time()*1000)}",
                notional=VIRTUAL_CAPITAL, pnl=pnl
            )
            logging.info(f"[Virtual] {strategy_name} 結算 PnL: {pnl:.2f} U")

        new_entry_price = price if target_pos != 0 else 0
        self.db.save_strategy_state(strategy_name, target_pos, new_entry_price, 0)
        logging.info(f"[Virtual] {strategy_name} 狀態更新: {current_pos} -> {target_pos}")

    def log_snapshot(self, ref_price):
        # ... (保持原本邏輯) ...
        try:
            info = self.executor.get_account_info()
            wallet_balance = float(info.get('totalWalletBalance', 0))
            margin_balance = float(info.get('totalMarginBalance', 0))
            unrealized_pnl = margin_balance - wallet_balance
            real_qty = self.executor.get_current_position(self.symbol)
            positions_data = {
                "symbol": self.symbol,
                "real_position": real_qty,
                "leverage": self.config.get("risk", "leverage", 1)
            }
            self.db.log_snapshot(wallet_balance, unrealized_pnl, ref_price, positions_data)
        except Exception as e:
            logging.error(f"[Snapshot Error] {e}")