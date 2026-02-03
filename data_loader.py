import pandas as pd
from binance.um_futures import UMFutures
from utils.database import DatabaseHandler

class DataLoader:
    def __init__(self, client: UMFutures, db: DatabaseHandler):
        self.client = client
        self.db = db # 現在需要傳入 DB Handler

    def get_binance_klines(self, symbol, interval, limit=100):
        """ 
        幣安 K 線維持直接抓取 (為了實盤即時性)，
        但建議同時也寫入 DB (ETL 流程在 main.py 做) 
        """
        try:
            klines = self.client.klines(symbol=symbol, interval=interval, limit=limit)
            df = pd.DataFrame(klines, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume', 
                'close_time', 'q_vol', 'trades', 'taker_buy_vol', 'taker_buy_q_vol', 'ignore'
            ])
            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            df[numeric_cols] = df[numeric_cols].astype(float)
            
            # 確保時間是整數 (API 回傳就是毫秒整數，不用動)
            return df
        except Exception as e:
            print(f"❌ 幣安數據抓取失敗: {e}")
            return pd.DataFrame()

    # ==========================================
    # 👇 改成從 DB 讀取的方法
    # ==========================================

    def get_google_trends_from_db(self, limit=1):
        """ 從 DB 讀取最新的 Google Trends """
        return self.db.load_external_data(
            symbol='GLOBAL', 
            metric='google_trends', 
            limit=limit
        )

    def get_fear_and_greed_from_db(self, limit=1):
        """ 從 DB 讀取恐慌指數 """
        return self.db.load_external_data(
            symbol='GLOBAL', 
            metric='fear_greed', 
            limit=limit
        )

    def get_macro_data_from_db(self, limit=1):
        """ 
        從 DB 讀取總經數據 
        因為 metric 有很多種，這裡可以一次讀出來
        """
        metrics = ['fed_assets', 'yield_10y', 'yield_2y']
        results = {}
        
        for m in metrics:
            df = self.db.load_external_data(symbol='US_MACRO', metric=m, limit=limit)
            if not df.empty:
                results[m] = df.iloc[-1]['value'] # 取最新一筆
            else:
                results[m] = 0
        return results

    def get_qqq_klines_from_db(self, limit=100):
        """ 從 market_data 表讀取 QQQ """
        return self.db.load_market_data(symbol='QQQ', interval='1d', limit=limit)