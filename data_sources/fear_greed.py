import requests
import pandas as pd
from .base_source import BaseDataSource

class FearGreedFetcher(BaseDataSource):
    name = "fear_greed"
    def __init__(self):
        
        self.url = "https://api.alternative.me/fng/"

    def fetch_data(self, limit=100):
        # 1. 呼叫第三方 API
        url = f"https://api.alternative.me/fng/?limit={limit}"
        response = requests.get(url).json()
        
        # 2. 處理數據
        data_list = response['data']
        df = pd.DataFrame(data_list)
        
        # 3. 標準化欄位
        result_df = pd.DataFrame()
        # API 給的是秒，轉毫秒
        result_df['open_time'] = df['timestamp'].astype('int64') * 1000 
        result_df['symbol'] = 'GLOBAL'      # 這種大盤數據通常不分幣種
        result_df['metric'] = 'fear_greed'  # 定義 Metric 名稱
        result_df['value'] = df['value'].astype(float)
        
        return result_df