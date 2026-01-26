import logging
import uuid
import time

class MockExecutor:
    def __init__(self):
        # 在記憶體中模擬帳本
        # 格式: {'BTCUSDT': 0.0, 'ETHUSDT': 0.0}
        self.positions = {} 
        logging.info(" [Mock Mode] 模擬執行器已啟動，所有訂單均為虛擬。")

    def get_current_position(self, symbol):
        """
        模擬查詢持倉
        """
        pos = self.positions.get(symbol, 0.0)
        # logging.info(f" [Mock] 查詢持倉 {symbol}: {pos}")
        return pos

    def execute_order(self, symbol, side, quantity, reduce_only=False):
        """
        模擬下單
        """
        logging.info(f" [Mock] 收到訂單請求: {side} {quantity} {symbol} (ReduceOnly={reduce_only})")
        
        # 模擬網路延遲
        time.sleep(0.5)
        
        # 更新本地虛擬持倉
        current_pos = self.positions.get(symbol, 0.0)
        
        if side == 'BUY':
            self.positions[symbol] = current_pos + quantity
        elif side == 'SELL':
            # 如果是 reduce_only (平倉)，確保不會賣過頭變成做空
            if reduce_only:
                new_pos = max(0, current_pos - quantity)
                self.positions[symbol] = new_pos
            else:
                self.positions[symbol] = current_pos - quantity

        # 模擬幣安回傳的訂單格式
        fake_order = {
            'orderId': str(uuid.uuid4())[:8], # 隨機產生一個 ID
            'symbol': symbol,
            'status': 'FILLED',
            'origQty': quantity,
            'side': side,
            'type': 'MARKET'
        }
        
        logging.info(f" [Mock] 訂單成交！虛擬持倉變更為: {self.positions[symbol]}")
        return fake_order

    def get_position_details(self, symbol):
        # 模擬回傳詳細結構
        amt = self.positions.get(symbol, 0.0)
        return {
            'amt': amt,
            'entryPrice': 93000.0, # 假裝的
            'unRealizedProfit': 0.0,
            'leverage': 1
        }
        
    def execute_order(self, symbol, side, quantity, reduce_only=False, market_price=None):
        logging.info(f" [Mock] 收到訂單: {side} {quantity} {symbol}")
        time.sleep(0.2)
        
        # 決定成交價：如果有傳入市價就用市價，否則用預設的 93000
        fill_price = market_price if market_price else self.mock_price

        # 1. 更新虛擬持倉
        current_pos = self.positions.get(symbol, 0.0)
        if side == 'BUY':
            self.positions[symbol] = current_pos + quantity
        elif side == 'SELL':
            if reduce_only:
                self.positions[symbol] = max(0, current_pos - quantity)
            else:
                self.positions[symbol] = current_pos - quantity

        # 2. 計算虛擬成交金額 (使用傳進來的市價)
        notional_value = quantity * fill_price

        # 3. 回傳
        return {
            'orderId': str(uuid.uuid4())[:8],
            'symbol': symbol,
            'status': 'FILLED',
            'executedQty': quantity,
            'cumQuote': notional_value, 
            'side': side,
            'type': 'MARKET'
        }
   
    def fetch_order_status(self, symbol, order_id):
        # 模擬盤：直接假設已經全部成交
        # 在這裡我們需要知道之前的下單資訊，為了簡化，
        # 我們假設模擬盤總是瞬間成交，所以回傳一個 "完美的成交單"
        
        # 這裡有個小技巧：MockExecutor 要稍微改一下，把最後一筆訂單存起來
        # 但為了不改動太大，我們這裡直接回傳一個 "假設成交" 的數據
        
        return {
            'orderId': str(order_id),
            'status': 'FILLED',
            'executedQty': 0.002, # 這裡如果是動態的會更好，但在 main 裡面我們會處理
            'avgPrice': 93000.0,  # 模擬價格
            'notional': 186.0
        }
    
    def set_leverage(self, symbol, leverage):
        # 模擬盤什麼都不用做，假裝設定成功就好
        logging.info(f" [CONFIG] (Mock) 成功設定 {symbol} 槓桿為 {leverage}x")
        return {'symbol': symbol, 'leverage': leverage}