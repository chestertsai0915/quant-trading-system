from .base_source import BaseDataSource
import pandas as pd
from binance.um_futures import UMFutures

class FundingRateFetcher(BaseDataSource):
    name = "funding_rate"
    def __init__(self, client: UMFutures):
        self.client = client

    def fetch_data(self, symbol="BTCUSDT", limit=100):
        # 1. 呼叫 API
        data = self.client.funding_rate(symbol=symbol, limit=limit)
        
        # 2. 轉成 DataFrame
        df = pd.DataFrame(data)
        
        # 3. 標準化欄位 (這是最重要的一步！)
        result_df = pd.DataFrame()
        result_df['open_time'] = df['fundingTime'] # 這裡已經是毫秒
        result_df['symbol'] = df['symbol']
        result_df['metric'] = 'funding_rate'       # 🔥 定義 Metric 名稱
        result_df['value'] = df['fundingRate'].astype(float)
        
        return result_df