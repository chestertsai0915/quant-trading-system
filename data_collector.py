import os
import time
import logging
import traceback
from dotenv import load_dotenv
from binance.um_futures import UMFutures

# 引入專案模組
from utils.database import DatabaseHandler
from data_loader import DataLoader
from data_sources.registry import get_all_fetchers

# 設定 Logging (無表情符號版)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

load_dotenv()

class DataCollector:
    def __init__(self):
        logging.info("[START] Initializing Data Collector...")

        # 1. 資料庫連線
        self.db = DatabaseHandler("trading_data.db")
        
        # 2. Binance Client
        key = os.getenv('BINANCE_API_KEY')
        secret = os.getenv('BINANCE_SECRET_KEY')
        self.client = UMFutures(key=key, secret=secret)
        
        # 3. DataLoader
        self.loader = DataLoader(self.client, self.db)
        
        # 4. 外部數據源 (從 Registry 載入)
        self.fetchers = get_all_fetchers()
        logging.info(f"[INFO] Loaded external sources: {list(self.fetchers.keys())}")

        # 設定
        self.symbol = 'BTCUSDT'
        self.interval = '1h'
        
        # 計時器狀態
        self.last_market_update = 0
        self.last_external_update = 0
        
        # 更新頻率 (秒)
        self.market_update_interval = 60      # 每分鐘更新 K 線
        self.external_update_interval = 3600  # 每小時更新外部數據

    def collect_market_data(self):
        """ 收集 Binance K 線數據 """
        try:
            # 抓取最新的 200 筆 (確保能補上前一根剛收盤的)
            raw_df = self.loader.get_binance_klines(self.symbol, self.interval, limit=200)
            
            if not raw_df.empty:
                self.db.save_market_data(self.symbol, self.interval, raw_df)
                logging.info(f"[MARKET] Saved {self.symbol} {self.interval} data. Count: {len(raw_df)}")
            else:
                logging.warning(f"[MARKET] Received empty DataFrame for {self.symbol}")

        except Exception as e:
            logging.error(f"[MARKET ERROR] Failed to collect market data: {e}")

    def collect_external_data(self):
        """ 收集所有註冊的外部數據 """
        logging.info("[EXTERNAL] Starting batch update for external sources...")
        
        for name, fetcher in self.fetchers.items():
            try:
                # 呼叫 Fetcher
                # limit 設定為 10，僅作為持續收集用途，不需要抓太多歷史
                df = fetcher.fetch_data(limit=10)
                
                if df.empty:
                    logging.warning(f"[EXTERNAL] {name} returned empty data.")
                    continue

                # 寫入資料庫 (區分 K 線型態與通用型態)
                if name == 'us_stock_qqq':
                    # 美股 QQQ 視為市場 K 線數據
                    self.db.save_market_data(symbol='QQQ', interval='1d', df=df)
                    logging.info(f"[EXTERNAL] Saved {name} to market_data table.")
                else:
                    # 其他通用數據 (Funding Rate, FearGreed, Macro...)
                    self.db.save_generic_external_data(df)
                    logging.info(f"[EXTERNAL] Saved {name} to external_data table.")

            except Exception as e:
                logging.error(f"[EXTERNAL ERROR] Failed to update {name}: {e}")
                # 印出詳細錯誤以便除錯，但不中斷迴圈
                traceback.print_exc()

    def run(self):
        logging.info("[RUNNING] Data Collector is active. Press Ctrl+C to stop.")
        
        while True:
            try:
                current_time = time.time()

                # --- 任務 1: 市場數據更新 (高頻) ---
                if current_time - self.last_market_update > self.market_update_interval:
                    self.collect_market_data()
                    self.last_market_update = current_time

                # --- 任務 2: 外部數據更新 (低頻) ---
                if current_time - self.last_external_update > self.external_update_interval:
                    self.collect_external_data()
                    self.last_external_update = current_time

                # 避免 CPU 滿載，短暫休眠
                time.sleep(10)

            except KeyboardInterrupt:
                logging.info("[STOP] Data Collector stopped by user.")
                break
            except Exception as e:
                logging.error(f"[CRITICAL ERROR] Main loop crashed: {e}")
                time.sleep(30) # 發生嚴重錯誤時等待較長時間再重試

if __name__ == "__main__":
    collector = DataCollector()
    collector.run()