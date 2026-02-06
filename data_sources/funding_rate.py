from .base_source import BaseDataSource
import pandas as pd
import os
from binance.um_futures import UMFutures

class FundingRateFetcher(BaseDataSource):
    name = "funding_rate"
    
    def __init__(self): # 改成不需要外部傳入 client
        key = os.getenv('BINANCE_API_KEY')
        secret = os.getenv('BINANCE_SECRET_KEY')
        # 自己建立連線
        self.client = UMFutures(key=key, secret=secret)

    def fetch_data(self, symbol="BTCUSDT", limit=100):
        try:
            # 1. 呼叫 API
            data = self.client.funding_rate(symbol=symbol, limit=limit)
            
            # 2. 轉成 DataFrame
            df = pd.DataFrame(data)
            if df.empty: return pd.DataFrame()
            
            # 3. 標準化欄位
            result_df = pd.DataFrame()
            result_df['open_time'] = df['fundingTime'] 
            result_df['symbol'] = df['symbol']
            result_df['metric'] = 'funding_rate'
            result_df['value'] = df['fundingRate'].astype(float)
            
            return result_df
        except Exception as e:
            print(f"[FundingRate] Error: {e}")
            return pd.DataFrame()