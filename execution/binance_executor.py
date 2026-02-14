import logging
from binance.error import ClientError
from decimal import Decimal, ROUND_DOWN

class BinanceExecutor:
    def __init__(self, client):
        self.client = client
        self.symbol_info = {} # 快取交易對規則

    def _get_step_size(self, symbol):
        """ 獲取該幣種的數量精度 (Step Size) """
        if symbol not in self.symbol_info:
            try:
                info = self.client.exchange_info()
                for s in info['symbols']:
                    if s['symbol'] == symbol:
                        for f in s['filters']:
                            if f['filterType'] == 'LOT_SIZE':
                                self.symbol_info[symbol] = float(f['stepSize'])
                                break
            except Exception as e:
                logging.error(f"無法獲取精度資訊: {e}")
                return None
        
        return self.symbol_info.get(symbol)

    def round_quantity(self, symbol, quantity):
        """ 將數量修正為符合交易所精度的數值 """
        step_size = self._get_step_size(symbol)
        if step_size is None:
            return quantity
        
        # 使用 Decimal 進行精確的無條件捨去
        step_decimal = Decimal(str(step_size))
        qty_decimal = Decimal(str(quantity))
        
        # 量化處理
        rounded_qty = float(qty_decimal.quantize(step_decimal, rounding=ROUND_DOWN))
        return rounded_qty

    #  新增：獲取詳細持倉資訊 (給 Position Snapshot 用)
    def get_position_details(self, symbol):
        """
        回傳詳細持倉：數量、入場均價、未實現損益
        """
        try:
            positions = self.client.get_position_risk(symbol=symbol)
            for p in positions:
                if p['symbol'] == symbol:
                    return {
                        'amt': float(p['positionAmt']),
                        'entryPrice': float(p['entryPrice']),
                        'unRealizedProfit': float(p['unRealizedProfit']),
                        #  修改這裡：使用 .get() 加上預設值 1，避免 KeyError
                        'leverage': int(p.get('leverage', 1)) 
                    }
            return None
        except Exception as e:
            # 建議把這行改成 warning，這樣如果有錯你才會注意到，但不會洗版
            logging.warning(f" 查詢持倉詳情失敗 (可能是 API 缺欄位): {e}")
            return None

    #  修改：只回傳數量的簡化版 (給 main.py 邏輯判斷用)
    def get_current_position(self, symbol):
        details = self.get_position_details(symbol)
        if details:
            return details['amt']
        return 0.0

    def execute_order(self, symbol, side, quantity, reduce_only=False, market_price=None):
        # 這裡只負責 "發送"，回傳單號即可
        try:
            final_qty = self.round_quantity(symbol, quantity)
            if final_qty <= 0: return None

            logging.info(f" [ORDER] 發送訂單 | {side} {symbol} | Qty: {final_qty}")
            
            params = {
                'symbol': symbol, 'side': side, 'type': 'MARKET', 'quantity': final_qty
            }
            if reduce_only: params['reduceOnly'] = 'true'

            response = self.client.new_order(**params)
            return response # 這裡回傳的可能是未成交狀態，沒關係
            
        except Exception as e:
            logging.error(f"下單失敗: {e}")
            return None
        
    def fetch_order_status(self, symbol, order_id):
        """
        根據 Order ID 向交易所查詢最終成交結果
        """
        try:
            # 呼叫幣安 API 查詢訂單詳情
            order_info = self.client.query_order(symbol=symbol, orderId=order_id)
            
            # 解析最精確的成交資訊
            executed_qty = float(order_info.get('executedQty', 0))
            cum_quote = float(order_info.get('cumQuote', 0)) # 總成交金額
            status = order_info.get('status', 'UNKNOWN')
            
            avg_price = 0.0
            if executed_qty > 0:
                avg_price = cum_quote / executed_qty
            
            return {
                'orderId': str(order_id),
                'status': status,
                'executedQty': executed_qty,
                'avgPrice': avg_price,
                'notional': cum_quote
            }
        except Exception as e:
            logging.error(f"查詢訂單狀態失敗 (ID: {order_id}): {e}")
            return None
    
    def set_leverage(self, symbol, leverage):
        """
        設定交易所的槓桿倍數
        """
        try:
            # 呼叫幣安 API 修改槓桿
            response = self.client.change_leverage(
                symbol=symbol, 
                leverage=leverage
            )
            logging.info(f" [CONFIG] 成功設定 {symbol} 槓桿為 {leverage}x")
            return response
        except ClientError as e:
            logging.error(f" 設定槓桿失敗: {e.error_code} - {e.error_message}")
        except Exception as e:
            logging.error(f" 設定槓桿發生未知錯誤: {e}")

    def get_account_info(self):
        """
        從幣安獲取真實帳戶餘額
        """
        try:
            # 呼叫 API 取得合約帳戶資訊
            # 這裡回傳的是整個帳戶的詳細資訊
            # 我們需要過濾出 USDT 的餘額 (假設是用 USDT 本位)
            account_info = self.client.account()
            
            # 取得 USDT 資產
            total_wallet_balance = 0.0
            total_margin_balance = 0.0
            available_balance = 0.0
            
            for asset in account_info['assets']:
                if asset['asset'] == 'USDT':
                    total_wallet_balance = float(asset['walletBalance'])
                    total_margin_balance = float(asset['marginBalance'])
                    available_balance = float(asset['availableBalance'])
                    break
            
            # 回傳符合統一格式的字典
            return {
                'totalWalletBalance': total_wallet_balance,
                'totalMarginBalance': total_margin_balance,
                'availableBalance': available_balance
            }
            
        except Exception as e:
            logging.error(f" [Executor] 獲取帳戶資訊失敗: {e}")
            # 回傳一個安全預設值，避免程式崩潰
            return {
                'totalWalletBalance': 0.0,
                'totalMarginBalance': 0.0,
                'availableBalance': 0.0
            }