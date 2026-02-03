import pandas as pd
import time
from pytrends.request import TrendReq

from .base_source import BaseDataSource

class GoogleTrendsFetcher(BaseDataSource):
    name = "google_trends"
    def __init__(self):
        
        # tz=360 代表 CST/MDT，這裡用預設即可
        self.pytrends = TrendReq(hl='en-US', tz=360)

    def fetch_data(self, keyword='Bitcoin', limit=None):
        try:
            # 抓取過去 7 天 (now 7-d) 以獲得小時級別的數據
            self.pytrends.build_payload([keyword], cat=0, timeframe='now 7-d', geo='', gprop='')
            trend_data = self.pytrends.interest_over_time()

            if trend_data.empty:
                return pd.DataFrame()

            # 整理格式
            df = trend_data.reset_index()
            result_df = pd.DataFrame()
            
            # 時間轉毫秒
            result_df['open_time'] = df['date'].astype('int64') // 10**6 
            result_df['symbol'] = 'GLOBAL'
            result_df['metric'] = 'google_trends' # 統一指標名稱
            result_df['value'] = df[keyword].astype(float)

            return result_df

        except Exception as e:
            print(f"[GoogleTrends] 抓取失敗: {e}")
            return pd.DataFrame()