# backtesting/pure_engine.py (升級版)
import pandas as pd
import numpy as np
import logging

class VirtualAccount:
    """ 
    虛擬帳戶 (支援合約/雙向交易)
    """
    def __init__(self, initial_balance=10000.0, maker_fee=0.0002, taker_fee=0.0005):
        self.initial_balance = initial_balance
        self.balance = initial_balance  # 帳戶餘額 (已實現損益 + 本金)
        self.position = 0.0             # 持倉數量 (正=多, 負=空)
        self.avg_price = 0.0            # 持倉均價
        self.taker_fee = taker_fee
        self.equity_curve = []          # 權益曲線

    def mark_to_market(self, current_price, timestamp):
        """ 計算當前權益 (Equity) """
        # 未實現損益計算
        unrealized_pnl = 0
        if self.position > 0:   # 多單
            unrealized_pnl = (current_price - self.avg_price) * self.position
        elif self.position < 0: # 空單 (跌才賺)
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
        fee = notional * self.taker_fee # 假設都吃單

        # === 買入邏輯 (BUY / COVER) ===
        if side == 'BUY':
            cost = fee # 買入成本至少包含手續費
            
            # 情境 A: 身上有空單 (Position < 0) -> 這是平空 (Cover)
            if self.position < 0:
                # 這次買入能平掉多少空單?
                cover_qty = min(quantity, abs(self.position))
                
                # 計算平倉損益
                pnl = (self.avg_price - price) * cover_qty
                self.balance += pnl # 實現損益
                self.balance -= (cover_qty * price * self.taker_fee) # 扣手續費
                
                self.position += cover_qty # 負數加正數 = 接近0
                
                # 如果還有剩餘數量，則反手做多
                remaining_qty = quantity - cover_qty
                if remaining_qty > 0:
                    self._open_position('LONG', remaining_qty, price)

            # 情境 B: 身上無單或多單 -> 加倉做多
            else:
                self._open_position('LONG', quantity, price)

        # === 賣出邏輯 (SELL / SHORT) ===
        elif side == 'SELL':
            # 情境 A: 身上有多單 (Position > 0) -> 這是平多 (Close)
            if self.position > 0:
                close_qty = min(quantity, self.position)
                
                # 計算平倉損益
                pnl = (price - self.avg_price) * close_qty
                self.balance += pnl
                self.balance -= (close_qty * price * self.taker_fee)
                
                self.position -= close_qty
                
                # 如果還有剩，反手做空
                remaining_qty = quantity - close_qty
                if remaining_qty > 0:
                    self._open_position('SHORT', remaining_qty, price)
            
            # 情境 B: 身上無單或空單 -> 加倉做空
            else:
                self._open_position('SHORT', quantity, price)

    def _open_position(self, direction, quantity, price):
        """ 處理開倉/加倉 (更新均價) """
        notional = quantity * price
        fee = notional * self.taker_fee
        
        # 檢查保證金是否足夠 (簡易版：假設 1x 槓桿)
        # 注意：如果是反手單，Balance 已經在上面更新過了
        if self.balance < fee: 
            # logging.warning("資金不足支付手續費，無法開倉")
            return

        if direction == 'LONG':
            new_cost = quantity * price
            old_cost = self.position * self.avg_price
            self.avg_price = (old_cost + new_cost) / (self.position + quantity)
            self.position += quantity
            self.balance -= fee # 扣手續費
            
        elif direction == 'SHORT':
            # 空單累積：數量變多(負更負)，均價加權
            current_abs_pos = abs(self.position)
            new_cost = quantity * price
            old_cost = current_abs_pos * self.avg_price
            self.avg_price = (old_cost + new_cost) / (current_abs_pos + quantity)
            self.position -= quantity # 變更負
            self.balance -= fee # 扣手續費


class PureBacktestEngine:
    def __init__(self, df, initial_balance=10000.0):
        self.df = df
        self.account = VirtualAccount(initial_balance)

    def run(self, strategy_func):
        # logging.info("--- 開始回測 (Futures Mode) ---")
        
        for index, row in self.df.iterrows():
            current_price = row['close']
            current_time = row['datetime']
            
            # 1. 更新帳戶淨值
            equity = self.account.mark_to_market(current_price, current_time)
            
            # 2. 呼叫策略
            action, pct = strategy_func(row, self.account)
            
            # 3. 執行交易
            # 簡單資金管理：用目前權益的 pct% 下單
            # 注意：做空時，我們也是用 USDT 當保證金，所以計算邏輯類似
            
            if pct > 0:
                amount_usdt = equity * pct
                qty = amount_usdt / current_price
                
                if action == 'BUY':
                    self.account.execute('BUY', qty, current_price, "Signal")
                elif action == 'SELL':
                    self.account.execute('SELL', qty, current_price, "Signal")
                # 新增明確的 SHORT/COVER 指令 (其實 SELL/BUY 已經包含，但為了語意清晰)
                elif action == 'SHORT':
                    self.account.execute('SELL', qty, current_price, "Signal")
                elif action == 'COVER':
                    self.account.execute('BUY', qty, current_price, "Signal")