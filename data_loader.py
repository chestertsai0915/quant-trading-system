import pandas as pd
from binance.um_futures import UMFutures
# 👇 新增 pytrends
from pytrends.request import TrendReq
import time
import requests  
from fredapi import Fred
from alpha_vantage.timeseries import TimeSeries
import yfinance as yf
import os


class DataLoader:
    def __init__(self, client: UMFutures):
        self.client = client
        # 初始化 PyTrends
        self.pytrends = TrendReq(hl='en-US', tz=360)
        
        # 簡單的快取機制，避免被 Google Ban IP
        self.last_google_fetch_time = 0
        self.cached_trends = None
        #  新增：Fear & Greed Index 快取
        #  新增：恐慌指數快取 (F&G 指數一天更新一次，不需要一直抓)
        self.last_fng_fetch = 0
        self.cached_fng = None
        # 初始化 FRED
        # 嘗試從環境變數讀取，如果沒有則使用預設值 (為了方便你測試，我這裡先放你的 Key)
        fred_key = os.getenv('FRED_API_KEY', '37e86335977c415a0ad204e77a194e8b')
        self.fred = Fred(api_key=fred_key)
        #  新增：總經數據快取
        self.last_macro_fetch = 0
        self.cached_macro = None

        # 初始化 Alpha Vantage
        self.av_key = os.getenv('ALPHA_VANTAGE_KEY', 'E5VUD2IG0AV6U3WM')
        self.ts = TimeSeries(key=self.av_key, output_format='pandas')
        
        # QQQ 快取 (日線資料，一天抓一次就好)
        self.last_qqq_fetch = 0
        self.cached_qqq = None

    def get_binance_klines(self, symbol, interval, limit=100):
        """ (這部分保持不變) """
        try:
            klines = self.client.klines(symbol=symbol, interval=interval, limit=limit)
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'vol', 
                'close_time', 'q_vol', 'trades', 'taker_buy_vol', 'taker_buy_q_vol', 'ignore'
            ])
            numeric_cols = ['open', 'high', 'low', 'close', 'vol']
            df[numeric_cols] = df[numeric_cols].astype(float)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f" 幣安數據抓取失敗: {e}")
            return pd.DataFrame()

    def get_google_trends(self, keywords=['Bitcoin']):
        """
        抓取 Google 搜尋熱度
        注意：Google API 限制嚴格，這裡設定冷卻時間 (例如每 1 小時才更新一次)
        """
        current_time = time.time()
        # 如果距離上次抓取還不到 3600 秒 (1小時)，直接回傳舊資料
        if self.cached_trends is not None and (current_time - self.last_google_fetch_time < 3600):
            return self.cached_trends

        print(" 正在向 Google 請求趨勢資料 (這可能需要幾秒鐘)...")
        try:
            # 設定查詢：只查過去 7 天 (now 7-d) 以獲得小時級別的數據
            self.pytrends.build_payload(keywords, cat=0, timeframe='now 7-d', geo='', gprop='')
            
            trend_data = self.pytrends.interest_over_time()
            
            if not trend_data.empty:
                # 我們只需要「最新一筆」數據
                latest_data = trend_data.iloc[-1]
                
                # 轉成字典格式方便策略讀取 {'Bitcoin': 85, 'is_partial': False}
                result = latest_data.to_dict()
                
                self.cached_trends = result
                self.last_google_fetch_time = current_time
                return result
            else:
                return {}

        except Exception as e:
            print(f" Google Trends 抓取失敗 (可能被限流): {e}")
            # 失敗時回傳上一次的數據，如果沒有則回傳預設值
            return self.cached_trends if self.cached_trends else {'Bitcoin': 50}
    
    #  新增：抓取 Fear & Greed Index
    def get_fear_and_greed(self):
        """
        抓取 Alternative.me 的 Crypto Fear & Greed Index
        API: https://api.alternative.me/fng/?limit=1
        """
        current_time = time.time()
        # 設定 1 小時 (3600秒) 更新一次即可
        if self.cached_fng and (current_time - self.last_fng_fetch < 3600):
            return self.cached_fng

        # print(" 正在更新 Fear & Greed Index...") # 測試時可以打開
        try:
            # 實盤只需要抓最新一筆 (limit=1)
            url = "https://api.alternative.me/fng/?limit=1"
            response = requests.get(url, timeout=10)
            data = response.json()
            
            if data.get('metadata', {}).get('error') is None:
                # 取得最新數值
                latest = data['data'][0]
                
                result = {
                    'fng_value': float(latest['value']),       # 數值 (0-100)
                    'fng_class': latest['value_classification'] # 分類 (e.g., Extreme Fear)
                }
                
                self.cached_fng = result
                self.last_fng_fetch = current_time
                return result
            else:
                return {}

        except Exception as e:
            print(f" Fear & Greed 抓取失敗: {e}")
            # 回傳舊值，如果都沒有則回傳預設 50 (中立)
            return self.cached_fng if self.cached_fng else {'fng_value': 50, 'fng_class': 'Neutral'}
        
    # 👇 新增：抓取總經數據 (FRED)
    def get_macro_data(self):
        """
        抓取聯準會資產負債表與美債殖利率
        更新頻率：每 24 小時抓一次即可 (因為這些數據更新很慢)
        """
        current_time = time.time()
        # 86400秒 = 24小時
        if self.cached_macro and (current_time - self.last_macro_fetch < 86400):
            return self.cached_macro

        print(" 正在更新總經數據 (FRED)...")
        try:
            # 1. 聯準會總資產 (WALCL)
            # 實盤技巧：不用抓所有歷史，sort_order='desc' 抓最近幾筆即可
            walcl_series = self.fred.get_series('WALCL', sort_order='desc', limit=5)
            walcl_latest = walcl_series.iloc[0] if not walcl_series.empty else 0

            # 2. 殖利率 (Yield Rates)
            # 你原本的 code 是用 monthly data (GS系列)，這裡保持一致
            # 但實盤通常會抓 'DGS10' (Daily) 會更即時，不過依照你的需求使用 GS
            yield_ids = {
                'yield_3m': 'TB3MS',
                'yield_2y': 'GS2',
                'yield_5y': 'GS5',
                'yield_10y': 'GS10'
            }
            
            yield_results = {}
            for key, series_id in yield_ids.items():
                s = self.fred.get_series(series_id, sort_order='desc', limit=5)
                yield_results[key] = s.iloc[0] if not s.empty else 0

            # 3. 計算 10年-2年 殖利率利差 (倒掛指標)
           

            result = {
                'fed_assets': walcl_latest,
                **yield_results 
            }

            self.cached_macro = result
            self.last_macro_fetch = current_time
            return result

        except Exception as e:
            print(f" FRED 數據抓取失敗: {e}")
            # 回傳舊值，如果沒有則給預設值
            return self.cached_macro if self.cached_macro else {
                'fed_assets': 0, 'yield_spread': 0, 
                'yield_10y': 0, 'yield_2y': 0
            }
        
    def get_qqq_data(self):
        """
        [Alpha Vantage 免費版模式]
        只抓取最近 100 筆日線資料 (Compact)
        """
        current_time = time.time()
        # 設定 12 小時 (43200秒) 更新一次，避免浪費每天 25 次的額度
        if self.cached_qqq is not None and (current_time - self.last_qqq_fetch < 43200):
            return self.cached_qqq

        print("🇺🇸 正在下載 QQQ 資料 (Alpha Vantage Compact)...")
        try:
            # ⚠️ 關鍵修改：不寫 outputsize (預設就是 compact)，或者顯式寫 outputsize='compact'
            # 這樣只會回傳最新的 100 筆數據
            data, meta = self.ts.get_daily(symbol='QQQ', outputsize='compact')
            
            # 欄位整理
            data = data.rename(columns={
                '1. open': 'open',
                '2. high': 'high',
                '3. low': 'low',
                '4. close': 'close',
                '5. volume': 'volume'
            })
            data = data.sort_index()

            # 時間處理 (完全依照你的邏輯)
            data.index = data.index + pd.DateOffset(hours=16)
            data.index = data.index.tz_localize('US/Eastern')
            data.index = data.index.tz_convert('UTC')
            
            self.cached_qqq = data
            self.last_qqq_fetch = current_time
            
            # Debug 用：確認抓到了幾筆
            # print(f"   [Debug] 成功抓取 QQQ 數據: {len(data)} 筆")
            
            return data

        except Exception as e:
            print(f"QQQ 資料抓取失敗: {e}")
            return self.cached_qqq if self.cached_qqq is not None else pd.DataFrame()