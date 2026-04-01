import os
import time
import logging
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from binance.um_futures import UMFutures

# 引入你的專案模組
from utils.database import DatabaseHandler
from data_sources.registry import get_all_fetchers
from data_sources.funding_rate import FundingRateFetcher

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

load_dotenv()

class DataForceBackfiller:
    def __init__(self):
        logging.info("[START] 初始化 2000 小時強制回補工具...")
        self.db = DatabaseHandler("trading_data.db")
        
        # Binance Client
        key = os.getenv('BINANCE_API_KEY')
        secret = os.getenv('BINANCE_SECRET_KEY')
        self.client = UMFutures(key=key, secret=secret)
        
        # 載入所有註冊的外部數據源
        self.fetchers = get_all_fetchers()
        
        # 特別補上不在 registry.py 中的 FundingRateFetcher
        if 'funding_rate' not in self.fetchers:
            self.fetchers['funding_rate'] = FundingRateFetcher()

        # 計算 2000 小時前的毫秒時間戳
        self.target_hours = 2000
        self.now_ms = int(datetime.now().timestamp() * 1000)
        self.start_ms = self.now_ms - (self.target_hours * 60 * 60 * 1000)

    def backfill_binance_klines(self, symbol="BTCUSDT", interval="1h"):
        """ 回補幣安 K 線 (分批抓取突破 1500 筆限制) """
        logging.info(f"========== 開始回補 {symbol} {interval} K線 ==========")
        logging.info(f"目標起點: {datetime.fromtimestamp(self.start_ms/1000).strftime('%Y-%m-%d %H:%M:%S')}")

        current_start = self.start_ms
        total_fetched = 0

        while current_start < self.now_ms:
            try:
                # 幣安單次上限 1500
                raw_data = self.client.klines(
                    symbol=symbol, 
                    interval=interval, 
                    startTime=current_start, 
                    endTime=self.now_ms,
                    limit=1500
                )
                
                if not raw_data:
                    break
                    
                columns = ['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 
                           'quote_asset_volume', 'number_of_trades', 'taker_buy_base', 'taker_buy_quote', 'ignore']
                df = pd.DataFrame(raw_data, columns=columns)
                
                # 寫入資料庫
                self.db.save_market_data(symbol, interval, df)
                
                fetched_count = len(df)
                total_fetched += fetched_count
                
                # 更新下一次抓取的起點 (最後一根 K 線時間 + 1小時)
                last_time = int(df['open_time'].max())
                current_start = last_time + (60 * 60 * 1000)
                
                logging.info(f"  -> 成功抓取並寫入 {fetched_count} 筆。目前進度到: {datetime.fromtimestamp(last_time/1000).strftime('%Y-%m-%d %H:%M')}")
                time.sleep(0.5) # 避免 Rate Limit

            except Exception as e:
                logging.error(f" 抓取 Binance K線失敗: {e}")
                break

        logging.info(f"{symbol} K線回補完成，共計 {total_fetched} 筆。\n")

    def backfill_external_data(self):
        """ 回補所有外部數據 (依據各自時框給予適當的 Limit) """
        logging.info("========== 開始回補外部數據 ==========")
        
        # 2000 小時大約是 84 天
        days_needed = (self.target_hours // 24) + 5 # 加上 5 天緩衝

        for name, fetcher in self.fetchers.items():
            try:
                logging.info(f" 正在回補外部數據: {name} ...")
                
                # 針對不同 API 決定合理的 limit
                if name == 'funding_rate':
                    # 資金費率通常 8 小時一次，2000小時約 250 次
                    fetch_limit = 300 
                else:
                    # 日線別數據 (QQQ, Fear/Greed, Fred) 
                    fetch_limit = days_needed # 約 90 筆

                df = fetcher.fetch_data(limit=fetch_limit)
                
                if df.empty:
                    logging.warning(f" {name} 回傳空數據，可能 API 達到限制或無歷史資料。")
                    continue
                
                # 依照 data_collector 的邏輯分流寫入
                if name == 'us_stock_qqq':
                    self.db.save_market_data(symbol='QQQ', interval='1d', df=df)
                    logging.info(f"  -> {name} 成功寫入 market_data ({len(df)} 筆)")
                else:
                    self.db.save_generic_external_data(df)
                    logging.info(f"  -> {name} 成功寫入 external_data ({len(df)} 筆)")

                time.sleep(1) # 各個外部 API 之間稍微暫停，避免並發請求過快

            except Exception as e:
                logging.error(f" 回補 {name} 時發生錯誤: {e}")

    def run(self):
        self.backfill_binance_klines("BTCUSDT", "1h")
        self.backfill_external_data()
        logging.info(" 所有 2000 小時歷史數據回補完畢！")

if __name__ == "__main__":
    backfiller = DataForceBackfiller()
    backfiller.run()