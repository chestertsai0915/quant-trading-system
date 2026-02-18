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
            cost = fee 
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
        self.pending_action = None # 用於存儲 T 時刻產生的訊號，留到 T+1 執行

    def run(self, strategy_func):
        # logging.info(f"--- 開始回測 (Mode: {self.mode}) ---")
        
        for index, row in self.df.iterrows():
            current_close = row['close']
            current_open = row['open']
            current_time = row['datetime']
            
            # ==========================================
            # 1. 執行 Pending Order (這是 T-1 時刻產生的訊號)
            # ==========================================
            if self.mode == 'next_open' and self.pending_action:
                action, pct = self.pending_action
                
                # 在 T 時刻的 Open 執行交易
                # 因為是在 Open 成交，我們用 Open Price 計算權益來決定下單量
                equity_at_open = self.account.mark_to_market(current_open, current_time)
                
                # 注意：mark_to_market 會寫入 equity_curve，但我們希望 equity_curve 紀錄的是收盤狀況
                # 所以這裡只是暫時計算，稍後會被 step 2 的收盤 mark 覆蓋或新增
                # 為了避免重複紀錄，我們可以不呼叫 mark_to_market，而是手動算 equity，
                # 但為了簡單起見，VirtualAccount 會 append 兩次，畫圖時通常取最後一次 (resample) 或是忽略中間過程
                # 這裡最簡單的做法是：直接用上一步的 equity 估算，或是只在執行時不紀錄 curve
                
                # 修正：直接執行，execute 內部會更新 balance/position
                self._process_order(action, pct, current_open, equity_at_open)
                
                self.pending_action = None # 清空訂單

            # ==========================================
            # 2. 更新權益 (Mark to Market) - 用收盤價結算
            # ==========================================
            # 這一步確保 equity_curve 紀錄的是每一根 K 線「收盤時」的狀態
            equity = self.account.mark_to_market(current_close, current_time)
            
            # ==========================================
            # 3. 呼叫策略 (產生訊號)
            # ==========================================
            res = strategy_func(row, self.account)
            if res is None: res = ('HOLD', 0)
            action, pct = res

            if action == 'HOLD' or pct <= 0:
                continue

            # ==========================================
            # 4. 處理訊號
            # ==========================================
            if self.mode == 'close':
                # [舊模式] 當下立刻用 Close 成交
                self._process_order(action, pct, current_close, equity)
            
            elif self.mode == 'next_open':
                # [新模式] 存起來，下一根 Open 才成交
                self.pending_action = (action, pct)

    def _process_order(self, action, pct, price, equity):
        """ 統一的下單處理邏輯 """
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