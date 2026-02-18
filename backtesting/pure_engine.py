# backtesting/pure_engine.py
import pandas as pd
import numpy as np

class VirtualAccount:
    """ 
    虛擬帳戶 (支援合約/雙向交易)
    """
    def __init__(self, initial_balance=10000.0, maker_fee=0.0002, taker_fee=0.0005):
        self.initial_balance = initial_balance
        self.balance = initial_balance  # 帳戶餘額 (已實現損益 + 本金)
        self.position = 0.0             # 持倉數量
        self.avg_price = 0.0            # 持倉均價
        self.taker_fee = taker_fee
        self.equity_curve = []          # 權益曲線

    def mark_to_market(self, current_price, timestamp):
        """ 計算當前權益 """
        unrealized_pnl = 0
        if self.position > 0:
            unrealized_pnl = (current_price - self.avg_price) * self.position
        elif self.position < 0:
            unrealized_pnl = (self.avg_price - current_price) * abs(self.position)
            
        total_equity = self.balance + unrealized_pnl
        
        self.equity_curve.append({
            'datetime': timestamp,
            'equity': total_equity,
            'price': current_price,
            'position': self.position
        })
        return total_equity

    def execute(self, side, quantity, price, reason):
        if quantity <= 0: return

        notional = quantity * price
        fee = notional * self.taker_fee

        if side == 'BUY':
            # 平空邏輯
            if self.position < 0: 
                cover_qty = min(quantity, abs(self.position))
                pnl = (self.avg_price - price) * cover_qty
                self.balance += pnl
                self.balance -= (cover_qty * price * self.taker_fee)
                self.position += cover_qty
                remaining_qty = quantity - cover_qty
                if remaining_qty > 0: self._open_position('LONG', remaining_qty, price)
            # 開多邏輯
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
                remaining_qty = quantity - close_qty
                if remaining_qty > 0: self._open_position('SHORT', remaining_qty, price)
            # 開空邏輯
            else: 
                self._open_position('SHORT', quantity, price)

    def _open_position(self, direction, quantity, price):
        notional = quantity * price
        fee = notional * self.taker_fee
        if self.balance < fee: return 

        if direction == 'LONG':
            new_cost = quantity * price
            old_cost = self.position * self.avg_price
            self.avg_price = (old_cost + new_cost) / (self.position + quantity)
            self.position += quantity
            self.balance -= fee
            
        elif direction == 'SHORT':
            current_abs_pos = abs(self.position)
            new_cost = quantity * price
            old_cost = current_abs_pos * self.avg_price
            self.avg_price = (old_cost + new_cost) / (current_abs_pos + quantity)
            self.position -= quantity
            self.balance -= fee


class PureBacktestEngine:
    def __init__(self, df, initial_balance=10000.0, mode='next_open'):
        """
        :param mode: 'close' (當根收盤成交) 或 'next_open' (次根開盤成交 - 較真實)
        """
        self.df = df
        self.account = VirtualAccount(initial_balance)
        self.mode = mode
        
        # 狀態暫存
        self.pending_action = None # Legacy: (action, pct)
        self.pending_target = None # New: target_pct (float)

    def run(self, strategy_func):
        # logging.info(f"--- 開始回測 (Mode: {self.mode}) ---")
        
        for index, row in self.df.iterrows():
            current_close = row['close']
            current_open = row['open']
            current_time = row['datetime']
            
            # ==========================================
            # 1. 執行 Pending Order (Next Open Mode)
            # ==========================================
            if self.mode == 'next_open':
                # 計算開盤時的權益 (用於計算張數)
                equity_at_open = self.account.mark_to_market(current_open, current_time)
                
                # A. 處理目標倉位 (Target Position)
                if self.pending_target is not None:
                    self._rebalance(self.pending_target, current_open, equity_at_open)
                    self.pending_target = None
                
                # B. 處理傳統訊號 (Action, Pct)
                elif self.pending_action is not None:
                    action, pct = self.pending_action
                    self._process_legacy_order(action, pct, current_open, equity_at_open)
                    self.pending_action = None

            # ==========================================
            # 2. 更新權益 (Mark to Market) - 用收盤價結算
            # ==========================================
            equity = self.account.mark_to_market(current_close, current_time)
            
            # ==========================================
            # 3. 呼叫策略 (產生訊號)
            # ==========================================
            signal = strategy_func(row, self.account)

            # ==========================================
            # 4. 處理訊號 (分流處理)
            # ==========================================
            
            # --- 情境 A: 新版 Target Position (回傳 float/int) ---
            if isinstance(signal, (int, float, np.number)):
                target_pct = float(signal)
                
                if self.mode == 'close':
                    self._rebalance(target_pct, current_close, equity)
                elif self.mode == 'next_open':
                    self.pending_target = target_pct

            # --- 情境 B: 舊版 Action Tuple (回傳 tuple) ---
            elif isinstance(signal, (tuple, list)):
                if signal is None: continue
                action, pct = signal
                if action == 'HOLD' or pct <= 0: continue

                if self.mode == 'close':
                    self._process_legacy_order(action, pct, current_close, equity)
                elif self.mode == 'next_open':
                    self.pending_action = (action, pct)

    def _rebalance(self, target_pct, price, equity):
        """
        核心調倉邏輯：計算 目標價值 vs 當前價值 的差額，自動買賣
        """
        # 1. 計算目標持倉價值
        target_val = equity * target_pct
        
        # 2. 計算目標數量
        target_qty = target_val / price
        
        # 3. 計算需要變動的數量 (Delta)
        current_qty = self.account.position
        delta_qty = target_qty - current_qty
        
        # 4. 執行交易
        # 設定一個極小閾值，避免浮點數誤差導致微小交易 (例如 0.000001 BTC)
        # 這裡假設小於 10 USDT 的變動就忽略 (可自行調整)
        if abs(delta_qty * price) < 10:
            return

        if delta_qty > 0:
            self.account.execute('BUY', delta_qty, price, "Rebalance Buy")
        elif delta_qty < 0:
            self.account.execute('SELL', abs(delta_qty), price, "Rebalance Sell")

    def _process_legacy_order(self, action, pct, price, equity):
        """ 舊版相容邏輯 """
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