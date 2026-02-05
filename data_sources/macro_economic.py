import pandas as pd
import os
from fredapi import Fred

from .base_source import BaseDataSource

class FredFetcher(BaseDataSource):
    name = "fred_macro"
    def __init__(self):
        
        key = os.getenv('FRED_API_KEY')
        self.fred = Fred(api_key=key)

    def fetch_data(self, limit=5):
        try:
            # 定義我們要抓的 Series ID 對應的 Metric 名稱
            series_map = {
                'WALCL': 'fed_assets',      # 聯準會資產
                'GS10': 'yield_10y',        # 10年期公債殖利率
                'GS2': 'yield_2y'           # 2年期公債殖利率
            }
            
            all_dfs = []

            for series_id, metric_name in series_map.items():
                # 抓取數據
                s = self.fred.get_series(series_id, sort_order='desc', limit=limit)
                if s.empty: continue

                # 轉成 DataFrame
                temp_df = s.to_frame(name='value').reset_index()
                temp_df.columns = ['date', 'value']
                
                # 格式化
                formatted_df = pd.DataFrame()
                formatted_df['open_time'] = temp_df['date'].astype('int64') // 10**6
                formatted_df['symbol'] = 'US_MACRO'
                formatted_df['metric'] = metric_name
                formatted_df['value'] = temp_df['value'].astype(float)
                
                all_dfs.append(formatted_df)

            if not all_dfs:
                return pd.DataFrame()

            # 合併所有指標
            final_df = pd.concat(all_dfs, ignore_index=True)
            return final_df

        except Exception as e:
            print(f"[FRED] 抓取失敗: {e}")
            return pd.DataFrame()