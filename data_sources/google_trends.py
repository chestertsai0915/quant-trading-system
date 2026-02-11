import pandas as pd
import time
import random
from pytrends.request import TrendReq
from .base_source import BaseDataSource

class GoogleTrendsFetcher(BaseDataSource):
    name = "google_trends"

    def __init__(self):
        # tz=360 代表 CST/MDT，這裡用預設即可
        # timeout 設定長一點避免連線逾時
        self.pytrends = TrendReq(hl='en-US', tz=360, timeout=(10,25))

    def fetch_data(self, keyword=None, limit=None):
        """
        一次抓取多個關鍵字並合併回傳
        keyword 參數這裡用不到，我們直接在內部定義要抓的清單
        """
        
        #  設定配置： { 'Metric名稱': '搜尋關鍵字' }
        # 您可以在這裡修改關鍵字，例如把 'Crypto' 改成 'Cryptocurrency'
        targets = {
            'google_trends_BTC': 'Bitcoin',
            'google_trends_crypto': 'Crypto'
        }

        all_dfs = []

        for metric_name, search_term in targets.items():
            try:
                #  Google Trends 非常容易鎖 IP (429 Error)
                # 每次請求前隨機休息 2~5 秒，降低被鎖機率
                sleep_time = random.randint(2, 5)
                time.sleep(sleep_time)

                # 抓取過去 7 天 (now 7-d) 以獲得小時級別的數據
                # cat=0 (所有類別), geo='' (全球)
                self.pytrends.build_payload([search_term], cat=0, timeframe='now 7-d', geo='', gprop='')
                
                trend_data = self.pytrends.interest_over_time()

                if trend_data.empty:
                    print(f"[GoogleTrends] {search_term} 抓不到數據")
                    continue

                # 整理格式
                df = trend_data.reset_index()
                
                # 建立標準格式 DataFrame
                temp_df = pd.DataFrame()
                
                # 時間轉毫秒
                temp_df['open_time'] = df['date'].astype('int64') // 10**6 
                temp_df['symbol'] = 'GLOBAL'
                
                #  關鍵修改：這裡填入對應的 Metric 名稱 (如 google_trends_BTC)
                temp_df['metric'] = metric_name 
                
                # 填入數值 (注意：interest_over_time 的欄位名稱就是搜尋關鍵字)
                temp_df['value'] = df[search_term].astype(float)

                all_dfs.append(temp_df)
                
                

            except Exception as e:
                print(f"[GoogleTrends] {metric_name} 抓取失敗: {e}")
                # 如果遇到 429 Too Many Requests，通常要休息很久
                if "429" in str(e):
                    print(" IP 可能被 Google 暫時封鎖，請稍後再試。")

        # 合併所有結果
        if all_dfs:
            return pd.concat(all_dfs, ignore_index=True)
        else:
            return pd.DataFrame()