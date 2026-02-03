import pandas as pd
import os
from alpha_vantage.timeseries import TimeSeries

from .base_source import BaseDataSource

class USStockFetcher(BaseDataSource):
    name = "us_stock_qqq"
    def __init__(self):
        key = os.getenv('ALPHA_VANTAGE_KEY')
        self.ts = TimeSeries(key=key, output_format='pandas')

    def fetch_data(self, symbol='QQQ', limit=100):
        try:
            # Alpha Vantage 每日額度有限，outputsize='compact' 只抓 100 筆
            data, meta = self.ts.get_daily(symbol=symbol, outputsize='compact')
            
            # 重命名欄位以符合 market_data 表結構
            data = data.rename(columns={
                '1. open': 'open',
                '2. high': 'high',
                '3. low': 'low',
                '4. close': 'close',
                '5. volume': 'volume'
            })
            
            # 處理 Index (時間)
            data.index = pd.to_datetime(data.index)
            # 加 16 小時調整為 UTC 收盤時間 (美股收盤通常是 UTC 20:00 - 21:00)
            # 這裡簡單處理，只要確保它是 datetime 物件即可，DatabaseHandler 會轉成 int
            
            # 轉成 market_data 需要的格式
            df = data.reset_index()
            df.rename(columns={'date': 'open_time'}, inplace=True)
            
            # 因為 BaseDataSource 規範是回傳 external_data 格式，
            # 但 QQQ 是 K 線，我們這裡做個例外，或者在 main.py 裡特別處理
            return df 

        except Exception as e:
            print(f"[AlphaVantage] 抓取失敗: {e}")
            return pd.DataFrame()