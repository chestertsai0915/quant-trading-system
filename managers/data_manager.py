import logging
import pandas as pd
import time
from data_sources.registry import get_all_fetchers
from data_loader import DataLoader

class DataManager:
    def __init__(self, client, db, symbol, interval):
        self.client = client
        self.db = db
        self.symbol = symbol
        self.interval = interval
        self.loader = DataLoader(self.client, self.db)
        self.fetchers = get_all_fetchers()
        self.last_processed_time = 0
        
        logging.info(f"載入外部數據源: {list(self.fetchers.keys())}")

    def get_history_klines(self, limit=1500):
        """ 獲取歷史 K 線 (熱機用) """
        return self.loader.get_binance_klines(self.symbol, self.interval, limit=limit)

    def check_new_candle(self):
        """ 
        偵測是否有新收盤的 K 線 
        Return: (bool, int, dataframe) -> (是否新K線, 收盤時間, 剛收盤的K線資料)
        """
        # 抓取最新的 2 根
        raw_df = self.loader.get_binance_klines(self.symbol, self.interval, limit=2)
        
        if raw_df.empty:
            return False, 0, None

        # 取得倒數第二根 (剛收盤的)
        latest_closed_kline = raw_df.iloc[-2]
        closed_time = int(latest_closed_kline['open_time'])

        if closed_time > self.last_processed_time:
            # 這是新 K 線
            return True, closed_time, raw_df.iloc[:-1] # 回傳排除未收盤的數據
        
        return False, 0, None

    def update_etl_process(self, closed_time, df_to_save):
        """ 執行標準 ETL 流程 """
        logging.info(f"[ETL] 處理新 K 線: {pd.to_datetime(closed_time, unit='ms')}")
        
        # 1. 存入 Market Data
        self.db.save_market_data(self.symbol, self.interval, df_to_save)
        
        # 2. 更新外部數據
        self._update_external_data()
        
        # 3. 讀回給策略用的數據
        #strategy_df = self.db.load_market_data(self.symbol, self.interval, limit=200)
        strategy_df = self.get_strategy_data(limit=200)
        # 更新內部狀態
        self.last_processed_time = closed_time
        
        return strategy_df

    def _update_external_data(self):
        """ 抓取外部數據並存檔 """
        for name, fetcher in self.fetchers.items():
            try:
                df = fetcher.fetch_data()
                if df.empty: continue

                if name == 'us_stock_qqq':
                    self.db.save_market_data(symbol='QQQ', interval='1d', df=df)
                else:
                    self.db.save_generic_external_data(df)
            except Exception as e:
                logging.error(f"外部數據更新失敗 [{name}]: {e}")

    def get_strategy_data(self, limit=200):
        """
        這是實盤與回測共用的數據準備邏輯
        功能：
        1. 讀取 K 線 (主時間軸)
        2. 讀取各種外部數據 (不同時間軸)
        3. 用 merge_asof 進行對齊 (等同於 ffill)
        """
        
        # 1. 讀取主 K 線 (你的 Time Anchor)
        df = self.db.load_market_data(self.symbol, self.interval, limit=limit)
        if df.empty: return pd.DataFrame()
        
        # 確保按時間排序 (merge_asof 的要求)
        df = df.sort_values('open_time')

        # 2. 準備外部數據列表
        # 這裡列出你想要合併的指標
        external_metrics = ['fear_greed', 'funding_rate', 'fed_assets', 'google_trends']
        
        # 取得 K 線的最早時間，我們只需要抓這之後的外部數據 (稍微多抓一點緩衝)
        start_time = int(df['open_time'].min()) - 86400000 # 多抓一天緩衝

        for metric in external_metrics:
            # A. 讀取該指標的數據
            # 注意：這裡可能回傳空 DataFrame (如果剛好這段時間沒數據)
            ext_df = self.db.load_external_data(
                symbol='GLOBAL' if metric != 'funding_rate' else self.symbol, 
                metric=metric, 
                start_time=start_time
            )
            
            if not ext_df.empty:
                ext_df = ext_df.sort_values('open_time')
                
                # B. 🔥 核心動作：merge_asof (向後查找)
                # 這就是在做 "Forward Fill"
                # 它會幫 df 的每一行，找到 ext_df 裡 open_time <= df.open_time 的最新一筆
                df = pd.merge_asof(
                    df,
                    ext_df[['open_time', 'value']], # 只取需要的欄位
                    on='open_time',
                    direction='backward', # 向後看 = 找過去最近的 = Last Known Value
                    suffixes=('', f'_{metric}')
                )
                
                # C. 欄位整理
                # merge_asof 會產生 'value' 或 'value_fear_greed' 這樣的欄位
                # 我們把它統一改成 metric 名稱
                target_col = f'value_{metric}' if f'value_{metric}' in df.columns else 'value'
                if target_col in df.columns:
                    df.rename(columns={target_col: metric}, inplace=True)
                
                # D. 補漏 (Fail-safe)
                # 如果 K 線最前面幾筆剛好沒有對應的外部數據 (因為 start_time 切太準)，會變成 NaN
                # 這時候用 ffill 補齊，確保不會有空值
                df[metric] = df[metric].ffill().fillna(0) # 真的都沒有就填 0
            
            else:
                # 如果資料庫完全沒有這個指標的數據，填 0 避免報錯
                df[metric] = 0

        return df