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
        strategy_df = self.db.load_market_data(self.symbol, self.interval, limit=200)
        
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