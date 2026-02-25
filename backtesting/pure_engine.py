# backtesting/pure_engine.py
import pandas as pd
import numpy as np

class VirtualAccount:
    """ 
    虛擬帳戶 (支援合約/雙向交易)
    """
    def __init__(self, initial_balance=10000.0, maker_fee=0.0002, taker_fee=0.0005):
        self.initial_balance = initial_balance
        self.balance = initial_balance  
        self.position = 0.0             
        self.avg_price = 0.0            
        self.taker_fee = taker_fee
        self.equity_curve = []          

    def mark_to_market(self, current_price, timestamp=None, record=False):
        unrealized_pnl = 0
        if self.position > 0:
            unrealized_pnl = (current_price - self.avg_price) * self.position
        elif self.position < 0:
            unrealized_pnl = (self.avg_price - current_price) * abs(self.position)
            
        total_equity = self.balance + unrealized_pnl
        
        if record and timestamp is not None:
            self.equity_curve.append({
                'datetime': timestamp,
                'equity': total_equity,
                'price': current_price,
                'position': self.position
            })
        return total_equity

    def execute(self, side, quantity, price, reason):
        if quantity <= 0: return

        if side == 'BUY':
            # 平空邏輯
            if self.position < 0: 
                cover_qty = min(quantity, abs(self.position))
                pnl = (self.avg_price - price) * cover_qty
                self.balance += pnl
                self.balance -= (cover_qty * price * self.taker_fee)
                self.position += cover_qty
                
                # 【新增防呆】完全平倉時，徹底重置均價 (消滅幽靈價格)
                if self.position == 0:
                    self.avg_price = 0.0
                    
                remaining_qty = quantity - cover_qty
                if remaining_qty > 0: 
                    self._open_position('LONG', remaining_qty, price)
            # 開多 / 加多邏輯
            else: 
                self._open_position('LONG', quantity, price)

        elif side == 'SELL':
            # 平多邏輯
            if self.position > 0: 
                close_qty = min(quantity, self.position)
                pnl = (price - self.avg_price) * close_qty
                self.balance += pnl
                self.balance -= (close_qty * price * self.taker_fee)
                self.position -= close_qty
                
                # 【新增防呆】完全平倉時，徹底重置均價 (消滅幽靈價格)
                if self.position == 0:
                    self.avg_price = 0.0
                    
                remaining_qty = quantity - close_qty
                if remaining_qty > 0: 
                    self._open_position('SHORT', remaining_qty, price)
            # 開空 / 加空邏輯
            else: 
                self._open_position('SHORT', quantity, price)

    def _open_position(self, direction, quantity, price):
        notional = quantity * price
        fee = notional * self.taker_fee
        
        # 嚴格購買力檢查
        required_margin = notional + fee
        if self.balance < required_margin: 
            return 

        # 【優化】均價計算邏輯改寫，變得超級白話、無歧義
        if self.position == 0:
            # 如果是從零開倉，均價就是當前的成交價
            self.avg_price = price
        else:
            # 如果是同向加倉，計算加權平均價 (VWAP)
            current_abs_pos = abs(self.position)
            old_cost = current_abs_pos * self.avg_price
            new_cost = quantity * price
            self.avg_price = (old_cost + new_cost) / (current_abs_pos + quantity)

        # 更新真實倉位與扣除手續費
        if direction == 'LONG':
            self.position += quantity
        elif direction == 'SHORT':
            self.position -= quantity
            
        self.balance -= fee


class PureBacktestEngine:
    def __init__(self, df, initial_balance=10000.0, mode='next_open'):
        self.df = df
        self.account = VirtualAccount(initial_balance)
        self.mode = mode
        
        self.pending_action = None 
        self.pending_target = None 

    def run(self, strategy_func):
        # 【修正問題 3】消滅 iterrows，改用 dict list 迭代，速度狂飆！
        # 這樣寫不僅極快，還完美相容策略檔中的 row.get('欄位')
        records = self.df.to_dict('records')
        
        for row in records:
            current_close = row['close']
            current_open = row['open']
            current_time = row['datetime']
            
            # ==========================================
            # 1. 執行 Pending Order (Next Open Mode)
            # ==========================================
            if self.mode == 'next_open':
                equity_at_open = self.account.mark_to_market(current_open)
                
                if self.pending_target is not None:
                    self._rebalance(self.pending_target, current_open, equity_at_open)
                    self.pending_target = None
                
                elif self.pending_action is not None:
                    action, pct = self.pending_action
                    self._process_legacy_order(action, pct, current_open, equity_at_open)
                    self.pending_action = None

            # ==========================================
            # 2. 更新權益 (Mark to Market) 
            # ==========================================
            equity = self.account.mark_to_market(current_close, current_time, record=True)
            
            # ==========================================
            # 3. 呼叫策略 (產生訊號)
            # ==========================================
            # 因為 records 是 dict，這裡傳進去的 row 完美支援 row.get()
            signal = strategy_func(row, self.account)

            # ==========================================
            # 4. 處理訊號 (分流處理)
            # ==========================================
            if isinstance(signal, (int, float, np.number)):
                target_pct = float(signal)
                if self.mode == 'close':
                    self._rebalance(target_pct, current_close, equity)
                elif self.mode == 'next_open':
                    self.pending_target = target_pct

            elif isinstance(signal, (tuple, list)):
                action, pct = signal
                if action != 'HOLD' and pct > 0:
                    if self.mode == 'close':
                        self._process_legacy_order(action, pct, current_close, equity)
                    elif self.mode == 'next_open':
                        self.pending_action = (action, pct)

    def _rebalance(self, target_pct, price, equity):
        """
        核心調倉邏輯：包含比例容忍度與微小價值過濾
        """
        # 1. 避免權益為 0 導致除以零錯誤
        if equity <= 0: 
            return

        # 2. 計算目前的實際倉位比例 (Current Weight)
        current_val = self.account.position * price
        current_pct = current_val / equity

        # 3. 核心升級：加入容忍度 (Tolerance Threshold)
        # 設定 5% (0.05) 的容忍度。只要倉位偏移不超過 5%，就不浪費手續費調倉
        TOLERANCE = 0.05 

        # 如果目標不是要完全平倉 (0.0)，且目前的曝險比例與目標差距在容忍度內，直接跳過！
        if abs(target_pct) > 1e-6 and abs(target_pct - current_pct) < TOLERANCE:
            return

        # 4. 正常計算目標數量與差額
        target_val = equity * target_pct
        target_qty = target_val / price
        current_qty = self.account.position
        delta_qty = target_qty - current_qty
        
        # 5. 執行門檻過濾 (低於 10U 的變動不交易)
        MIN_TRADE_VALUE = 10.0
        delta_value = abs(delta_qty * price)

        # 實盤級別的細節：如果目標是 0 (完全平倉)，即使剩下的部位價值不到 10U，也必須強制平掉 (清掃灰塵)
        if abs(target_pct) < 1e-6 and abs(current_qty) > 1e-6:
            pass # 強制放行
        elif delta_value < MIN_TRADE_VALUE:
            return # 變動太小，跳過

        # 6. 執行交易
        if delta_qty > 0:
            self.account.execute('BUY', delta_qty, price, "Rebalance Buy")
        elif delta_qty < 0:
            self.account.execute('SELL', abs(delta_qty), price, "Rebalance Sell")

    def _process_legacy_order(self, action, pct, price, equity):
        if action in ['LONG', 'SHORT']:
            target_notional = equity * pct
            qty = target_notional / price
            
            if action == 'LONG':
                self.account.execute('BUY', qty, price, "Long Entry")
            elif action == 'SHORT':
                self.account.execute('SELL', qty, price, "Short Entry")

        elif action == 'LONG_EXIT':
            if self.account.position > 0:
                close_qty = self.account.position * pct
                self.account.execute('SELL', close_qty, price, "Long Exit")

        elif action == 'SHORT_EXIT':
            if self.account.position < 0:
                cover_qty = abs(self.account.position) * pct
                self.account.execute('BUY', cover_qty, price, "Short Exit")