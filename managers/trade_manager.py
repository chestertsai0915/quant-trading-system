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
        self.portfolio_manager = PortfolioManager(config, db) # <--- 初始化 PortfolioManager
        
        # 設定交易所槓桿
        if not self.is_paper:
            self.executor.set_leverage(self.symbol, config.get("risk", "leverage", 1))

    def process_signal(self, signal_data):
        """
        處理訊號的核心邏輯 (支援多策略互抵 + 影子交易模式)
        """
        strategy_name = signal_data['strategy_name']
        action = signal_data['action'] # 'LONG', 'SHORT', 'CLOSE', 'FLAT'
        ref_price = signal_data['ref_price']
        
        # A. 取得當前帳戶總權益 (Real Equity)
        account_info = self.executor.get_account_info()
        total_equity = float(account_info['totalWalletBalance']) if account_info else 1000.0
        
        # B. 計算該策略「目標持有金額」
        # 如果是被淘汰的策略，這裡會回傳 0
        allocated_usdt = self.portfolio_manager.calculate_allocation(strategy_name, total_equity)
        
        #  判斷是否進入「影子模式 (Shadow Mode)」
        is_shadow_mode = (allocated_usdt == 0)
        
        # C. 計算「本次計算用的本金」
        # 如果是真交易 -> 用分配到的錢
        # 如果是影子交易 -> 用「模擬本金 (1000U)」來計算「假設我有錢會買多少」
        # 這樣才能累積 PnL，讓它有機會敗部復活
        trading_capital = allocated_usdt if not is_shadow_mode else 1000.0

        # D. 計算該策略「目標持倉數量 (Virtual Target Qty)」
        target_strategy_qty = 0.0
        
        if action == 'LONG':
            target_strategy_qty = self.risk_manager.calculate_quantity(ref_price, trading_capital)
        elif action == 'SHORT':
            target_strategy_qty = -self.risk_manager.calculate_quantity(ref_price, trading_capital)
        elif action == 'CLOSE' or action == 'FLAT':
            target_strategy_qty = 0.0
            
        # E. 讀取該策略「目前虛擬持倉」
        #  注意：改用 get_strategy_state (讀取新表) 而不是 get_strategy_position
        current_strategy_qty, _, _ = self.db.get_strategy_state(strategy_name)
        logging.info(f"[SIGNAL] {strategy_name} ({ref_price}) | {action} | {signal_data.get('reason', 'No Reason')}")
        # 如果目標跟現在一樣，就不做動作
        if target_strategy_qty == current_strategy_qty:
            # 情境 1: 訊號是平倉 (CLOSE/FLAT)，但目前是空手 (0)
            if current_strategy_qty == 0 and (action == 'CLOSE' or action == 'FLAT'):
                logging.info(f"[SKIP] {strategy_name} 目前空手，無法平倉/無需動作")
            
            # 情境 2: 訊號是開倉 (LONG/SHORT)，但已經持倉且數量沒變 (可能是沒錢加倉，或訊號重複)
            elif current_strategy_qty != 0:
                logging.info(f"[SKIP] {strategy_name} 已有持倉 {current_strategy_qty}，部位無變化")
            
            # 情境 3: 其他 (例如 Shadow Mode 權重為 0，導致 target=0 且 current=0)
            else:
                if is_shadow_mode:
                     logging.info(f"[SKIP] {strategy_name} (觀察中) 無動作")
                else:
                     logging.info(f"[SKIP] {strategy_name} 無需調倉")

            return

        # F. 計算「策略需要調整的量 (Delta)」
        delta_qty = target_strategy_qty - current_strategy_qty
        
        # G. 分流執行
        if is_shadow_mode:
            logging.info(f"[Shadow] {strategy_name} 處於觀察期，執行模擬調倉: {delta_qty}")
            self._execute_shadow_order(strategy_name, delta_qty, ref_price)
        else:
            logging.info(f"[Portfolio] {strategy_name} 執行真實調倉: {current_strategy_qty} -> {target_strategy_qty} (Delta: {delta_qty})")
            self._execute_net_order(strategy_name, delta_qty, ref_price)

    def log_snapshot(self, ref_price):
        """
        [新增] 記錄資產快照
        這是為了讓您能畫出「資金曲線圖」，在新架構下依然非常重要。
        """
        try:
            # 1. 取得真實帳戶權益
            info = self.executor.get_account_info()
            
            # 從 executor 拿到的通常是字串或浮點數，確保轉型
            wallet_balance = float(info.get('totalWalletBalance', 0))
            margin_balance = float(info.get('totalMarginBalance', 0))
            
            # 2. 計算未實現損益
            # 公式：未實現損益 = 總權益 (Margin Balance) - 錢包餘額 (Wallet Balance)
            unrealized_pnl = margin_balance - wallet_balance
            
            # 3. 取得目前真實持倉 (Real Position)
            real_qty = self.executor.get_current_position(self.symbol)
            
            # 4. 準備要存的 JSON 資料
            # 這裡我們紀錄真實持倉，未來除錯時很有用
            positions_data = {
                "symbol": self.symbol,
                "real_position": real_qty,
                "leverage": self.config.get("risk", "leverage", 1)
            }
            
            # 5. 寫入資料庫
            self.db.log_snapshot(
                balance=wallet_balance, 
                unrealized_pnl=unrealized_pnl, 
                btc_price=ref_price, 
                positions=positions_data
            )
            
        except Exception as e:
            logging.error(f"[Snapshot Error] 紀錄資產快照失敗: {e}")

    # 記得在 TradeManager 類別下方補上這個方法
    def _execute_shadow_order(self, strategy_name, delta_qty, price):
        """
        [影子下單] 不送幣安，只寫 DB，用於累積觀察期數據
        """
        if delta_qty == 0: return
        
        # 1. 判斷方向標籤 (為了 DB 紀錄好看)
        # 這裡邏輯與 _execute_net_order 保持一致，最好能抽成共用函式，這裡簡化寫法：
        current_pos, _, _ = self.db.get_strategy_state(strategy_name)
        db_side = 'LONG' # 預設
        if current_pos > 0 and delta_qty < 0: db_side = 'CLOSE'
        elif current_pos < 0 and delta_qty > 0: db_side = 'CLOSE'
        else: db_side = 'LONG' if delta_qty > 0 else 'SHORT'

        # 2. 直接更新帳本 (計算 PnL)
        # 這是最重要的一步！即使沒下單，也要算損益
        pnl = self.portfolio_manager.update_position_record(strategy_name, delta_qty, price)
        
        # 3. 寫入 Trades 表 (標記 order_id 為 shadow)
        import time
        self.db.log_trade(
            strategy=strategy_name,
            symbol=self.symbol,
            side=db_side,
            price=price,
            quantity=abs(delta_qty),
            order_id=f"shadow_{int(time.time()*1000)}", # 假單號
            notional=price * abs(delta_qty),
            pnl=pnl
        )

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

            # 呼叫 PortfolioManager 更新持倉並計算損益
            pnl = self.portfolio_manager.update_position_record(strategy_name, delta_qty, avg_price)

            # 3. 再紀錄 (把 pnl 存進去)
            self.db.log_trade(
                strategy=strategy_name,
                symbol=self.symbol,
                side=db_side,
                price=avg_price,
                quantity=qty_abs,
                order_id=f"v_{response['orderId']}",
                notional=avg_price * qty_abs,
                pnl=pnl  # <--- 把剛算出來的錢存進去！
            )
            
            
            
            msg = f"[調倉] {strategy_name}\n動作: {db_side} {qty_abs}\n價格: {avg_price}"
            if pnl != 0:
                msg += f"\n已實現損益: {pnl:.2f} U"
                
            send_tg_msg(msg)