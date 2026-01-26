# 👇 新增 pytrends
from pytrends.request import TrendReq
import time
keywords='Bitcoin'
"""
抓取 Google 搜尋熱度
注意：Google API 限制嚴格，這裡設定冷卻時間 (例如每 1 小時才更新一次)
"""
pytrends = TrendReq(hl='en-US', tz=360)
current_time = time.time()
# 如果距離上次抓取還不到 3600 秒 (1小時)，直接回傳舊資料


    # 設定查詢：只查過去 7 天 (now 7-d) 以獲得小時級別的數據
pytrends.build_payload(keywords, cat=0, timeframe='now 7-d', geo='', gprop='')

trend_data = pytrends.interest_over_time()

if not trend_data.empty:
    # 我們只需要「最新一筆」數據
    latest_data = trend_data.iloc[-1]
    
    # 轉成字典格式方便策略讀取 {'Bitcoin': 85, 'is_partial': False}
    result = latest_data.to_dict()
    
    cached_trends = result
    last_google_fetch_time = current_time
    print(trend_data)