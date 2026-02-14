# managers/trade_manager.py
import logging
import time
from utils.notifier import send_tg_msg
from execution.risk_manager import RiskManager
from execution.binance_executor import BinanceExecutor
from execution.mock_executor import MockExecutor
from .portfolio_manager import PortfolioManager  # <--- 新增引用

class TradeManager:
    def __init__(self, client, db, config, symbol, is_paper=False):
        self.client = client
        self.db = db
        self.config = config
        self.symbol = symbol
        self.is_paper = is_paper
        
        # 1. 初始化執行器
        if self.is_paper:
            self.executor = MockExecutor()
        else:
            self.executor = BinanceExecutor(self.client)
            
        # 2. 初始化管理器
        self.risk_manager = RiskManager(leverage=config.get("risk", "leverage", 1))
        self.portfolio_manager = PortfolioManager(config) # <--- 初始化 PortfolioManager
        
        # 設定交易所槓桿
        if not self.is_paper:
            self.executor.set_leverage(self.symbol, config.get("risk", "leverage", 1))

    def process_signal(self, signal_data):
        """
        處理訊號的核心邏輯 (支援多策略互抵)
        """
        strategy_name = signal_data['strategy_name']
        action = signal_data['action'] # 'LONG', 'SHORT', 'CLOSE', 'FLAT'
        ref_price = signal_data['ref_price']
        
        # A. 取得當前帳戶總權益 (Real Equity)
        # 用於計算等權重金額
        account_info = self.executor.get_account_info()
        total_equity = float(account_info['totalWalletBalance']) if account_info else 1000.0 # 預設值防呆
        
        # B. 計算該策略「目標持有金額」
        allocated_usdt = self.portfolio_manager.calculate_allocation(strategy_name, total_equity)
        
        # C. 計算該策略「目標持倉數量 (Virtual Target Qty)」
        # 這裡簡化邏輯：LONG 就是滿倉，FLAT/CLOSE 就是空手
        target_strategy_qty = 0.0
        
        if action == 'LONG':
            target_strategy_qty = self.risk_manager.calculate_quantity(ref_price, allocated_usdt)
        elif action == 'SHORT':
            target_strategy_qty = -self.risk_manager.calculate_quantity(ref_price, allocated_usdt)
        elif action == 'CLOSE' or action == 'FLAT':
            target_strategy_qty = 0.0
            
        # D. 讀取該策略「目前虛擬持倉 (Current Virtual Qty)」
        current_strategy_qty, _ = self.db.get_strategy_position(strategy_name, self.symbol)
        
        # 如果目標跟現在一樣，就不做動作
        if target_strategy_qty == current_strategy_qty:
            return

        # E. 計算「策略需要調整的量 (Delta)」
        delta_qty = target_strategy_qty - current_strategy_qty
        
        logging.info(f"[Portfolio] {strategy_name} 調整倉位: {current_strategy_qty} -> {target_strategy_qty} (Delta: {delta_qty})")

        # F. 執行「淨部位」下單 (Netting Execution)
        # 這裡我們做一個簡化：直接假設交易所可以執行這個 Delta
        # (完整的 Netting 系統會去算所有策略的總和，這裡為了相容性，我們先用 Delta 執行)
        self._execute_net_order(strategy_name, delta_qty, ref_price)

    def _execute_net_order(self, strategy_name, delta_qty, price):
        """
        執行差額下單，並分別紀錄「虛擬交易」與「真實成交」
        """
        if delta_qty == 0: return
        
        # 1. [新增] 先查詢該策略目前的持倉 (為了判斷是 LONG 還是 CLOSE)
        # 注意：這裡要用 get_strategy_state，因為這是最新的狀態
        current_pos, _, _ = self.db.get_strategy_state(strategy_name)

        side = 'BUY' if delta_qty > 0 else 'SELL'
        qty_abs = abs(delta_qty)
        
        # 2. 發送真實訂單到幣安 (Real Order)
        logging.info(f"[EXEC] 發送訂單: {side} {qty_abs} (由 {strategy_name} 觸發)")
        
        response = self.executor.execute_order(
            self.symbol, side, qty_abs, reduce_only=False, market_price=price
        )
        
        if response and response.get('orderId'):
            # 3. 紀錄「虛擬交易」到資料庫 (Virtual Log)
            
            # 模擬成交價
            avg_price = float(response.get('avgPrice', price))
            if avg_price == 0: avg_price = price
            
            # 4. [修改] 智慧判斷 db_side (LONG / SHORT / CLOSE)
            # 邏輯：看這次的 delta_qty 是否讓持倉絕對值變小？
            
            db_side = ''
            
            # A. 如果原本做多 (Pos > 0) 且 這次賣出 (Delta < 0) -> 平倉 (CLOSE)
            if current_pos > 0 and delta_qty < 0:
                db_side = 'CLOSE'
            
            # B. 如果原本做空 (Pos < 0) 且 這次買入 (Delta > 0) -> 平倉 (CLOSE)
            elif current_pos < 0 and delta_qty > 0:
                db_side = 'CLOSE'
            
            # C. 其他情況 (原本是 0，或是加倉) -> 根據方向決定 LONG 或 SHORT
            else:
                db_side = 'LONG' if delta_qty > 0 else 'SHORT'

            # 5. 寫入資料庫
            self.db.log_trade(
                strategy=strategy_name,
                symbol=self.symbol,
                side=db_side,   # 這裡現在會是正確的 LONG/SHORT/CLOSE
                price=avg_price,
                quantity=qty_abs,
                order_id=f"v_{response['orderId']}",
                notional=avg_price * qty_abs
            )
            
            # 6. [新增] 同步呼叫 PortfolioManager 更新帳本與損益 (這是我們上一段加的)
            # 這樣才會把 realized_pnl 算出來存進 strategy_states
            pnl = self.portfolio_manager.update_position_record(strategy_name, delta_qty, avg_price)
            
            msg = f"[調倉] {strategy_name}\n動作: {db_side} {qty_abs}\n價格: {avg_price}"
            if pnl != 0:
                msg += f"\n已實現損益: {pnl:.2f} U"
                
            send_tg_msg(msg)