import logging
import uuid
import time

class MockExecutor:
    def __init__(self, initial_balance=100000.0):
        # 真正的模擬帳本
        self.wallet_balance = initial_balance
        self.positions = {}      # 紀錄各幣種持倉數量
        self.avg_prices = {}     # 紀錄各幣種開倉均價
        self.last_price = {}     # 紀錄各幣種最新市價 (算浮盈用)
        self.fee_rate = 0.0005   # 模擬萬分之五 (0.05%) 的手續費
        logging.info(f" [Mock Mode] 具備記帳能力的模擬執行器已啟動，初始資金: {self.wallet_balance} U")

    def set_mark_price(self, symbol, price):
        """ 讓外部 (如回測器) 即時更新當下價格，以精準計算未實現損益 """
        self.last_price[symbol] = price

    def get_current_position(self, symbol):
        return self.positions.get(symbol, 0.0)

    def get_account_info(self):
        """ 動態計算最新資金與未實現損益 (Unrealized PnL) """
        unrealized_pnl = 0.0
        for sym, pos in self.positions.items():
            if pos != 0 and sym in self.last_price:
                mark_price = self.last_price[sym]
                avg_price = self.avg_prices.get(sym, 0.0)
                if pos > 0:
                    unrealized_pnl += (mark_price - avg_price) * pos
                elif pos < 0:
                    unrealized_pnl += (avg_price - mark_price) * abs(pos)

        # 總權益 = 錢包真實餘額 + 未實現浮盈
        margin_balance = self.wallet_balance + unrealized_pnl

        return {
            'totalWalletBalance': self.wallet_balance,
            'totalMarginBalance': margin_balance,
            'availableBalance': self.wallet_balance
        }

    def execute_order(self, symbol, side, quantity, reduce_only=False, market_price=None):
        logging.info(f" [Mock] 收到訂單: {side} {quantity} {symbol}")
        
        # 1. 決定成交價，並更新最新價格快取
        fill_price = market_price if market_price else self.last_price.get(symbol, 93000.0)
        self.last_price[symbol] = fill_price

        current_pos = self.positions.get(symbol, 0.0)
        avg_price = self.avg_prices.get(symbol, 0.0)

        # 2. 扣除手續費
        notional_value = quantity * fill_price
        fee = notional_value * self.fee_rate
        self.wallet_balance -= fee

        # 3. 處理部位增減與 Realized PnL
        if side == 'BUY':
            if current_pos < 0: # 平空
                cover_qty = min(quantity, abs(current_pos))
                realized_pnl = (avg_price - fill_price) * cover_qty
                self.wallet_balance += realized_pnl
                
                new_pos = current_pos + quantity
                if new_pos > 0: # 翻多
                    self.avg_prices[symbol] = fill_price
                elif new_pos == 0:
                    self.avg_prices[symbol] = 0.0
                self.positions[symbol] = new_pos
            else: # 加多
                new_cost = (current_pos * avg_price) + (quantity * fill_price)
                new_pos = current_pos + quantity
                self.avg_prices[symbol] = new_cost / new_pos if new_pos > 0 else 0
                self.positions[symbol] = new_pos

        elif side == 'SELL':
            if current_pos > 0: # 平多
                close_qty = min(quantity, current_pos)
                realized_pnl = (fill_price - avg_price) * close_qty
                self.wallet_balance += realized_pnl
                
                new_pos = current_pos - quantity
                if new_pos < 0: # 翻空
                    self.avg_prices[symbol] = fill_price
                elif new_pos == 0:
                    self.avg_prices[symbol] = 0.0
                self.positions[symbol] = new_pos
            else: # 加空
                current_abs = abs(current_pos)
                new_cost = (current_abs * avg_price) + (quantity * fill_price)
                new_pos = current_pos - quantity
                self.avg_prices[symbol] = new_cost / abs(new_pos) if abs(new_pos) > 0 else 0
                self.positions[symbol] = new_pos

        return {
            'orderId': str(uuid.uuid4())[:8],
            'symbol': symbol,
            'status': 'FILLED',
            'executedQty': quantity,
            'cumQuote': notional_value, 
            'side': side,
            'type': 'MARKET'
        }

    def get_position_details(self, symbol):
        return {
            'amt': self.positions.get(symbol, 0.0),
            'entryPrice': self.avg_prices.get(symbol, 0.0),
            'unRealizedProfit': 0.0, 
            'leverage': 1
        }

    def fetch_order_status(self, symbol, order_id):
        return {
            'orderId': str(order_id),
            'status': 'FILLED',
            'executedQty': 0.002,
            'avgPrice': self.last_price.get(symbol, 93000.0),
            'notional': 186.0
        }
    
    def set_leverage(self, symbol, leverage):
        return {'symbol': symbol, 'leverage': leverage}