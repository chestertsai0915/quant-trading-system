import os
import time
import logging
import sqlite3
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from binance.um_futures import UMFutures

# 引入你的專案模組
from utils.database import DatabaseHandler
from data_sources.registry import get_all_fetchers

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

load_dotenv()

INTERVAL_MS_MAP = {
    "1m": 60 * 1000,
    "5m": 5 * 60 * 1000,
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}

class DataBackfiller:
    def __init__(self):
        logging.info("[START] 初始化補資料工具...")
        self.db = DatabaseHandler("trading_data.db")
        
        # Binance Client
        key = os.getenv('BINANCE_API_KEY')
        secret = os.getenv('BINANCE_SECRET_KEY')
        self.client = UMFutures(key=key, secret=secret)
        
        # 外部數據源
        self.fetchers = get_all_fetchers()

    def find_missing_blocks(self, df, interval, time_col='open_time'):
        """ 尋找資料庫中遺失的時間區塊，並整理成 [start, end] 的連續段落 """
        if df.empty:
            return []

        first_time = df[time_col].min()
        ms_per_interval = INTERVAL_MS_MAP.get(interval, 3600000)
        
        now_ms = int(datetime.now().timestamp() * 1000)
        last_theoretical_time = (now_ms // ms_per_interval) * ms_per_interval

        # 理論上應有的完整時間序列
        expected_times = range(first_time, last_theoretical_time + ms_per_interval, ms_per_interval)
        expected_df = pd.DataFrame({time_col: expected_times})

        # 找出缺失的時間點
        missing_df = expected_df[~expected_df[time_col].isin(df[time_col])].copy()
        
        if missing_df.empty:
            return []

        # 將連續的缺失時間點打包成區塊 (Blocks)
        missing_df = missing_df.sort_values(time_col)
        missing_df['diff'] = missing_df[time_col].diff()
        
        # 如果相鄰兩個缺失點的距離大於一個 interval，代表是不同的斷層區塊
        missing_df['block'] = (missing_df['diff'] > ms_per_interval).cumsum()
        
        blocks = []
        for _, group in missing_df.groupby('block'):
            blocks.append({
                'start_time': int(group[time_col].min()),
                'end_time': int(group[time_col].max()),
                'count': len(group)
            })
            
        return blocks

    def backfill_binance_market_data(self, symbol, interval):
        """ 補齊幣安的 K 線數據 """
        logging.info(f"🔍 檢查 {symbol} ({interval}) 的市場數據...")
        
        query = f"SELECT open_time FROM market_data WHERE symbol='{symbol}' AND interval='{interval}'"
        conn = sqlite3.connect(self.db.db_path)
        df = pd.read_sql(query, conn)
        conn.close()

        blocks = self.find_missing_blocks(df, interval)
        if not blocks:
            logging.info(f"✅ {symbol} ({interval}) 資料完整，無需補齊。")
            return

        logging.warning(f"⚠️ 發現 {symbol} 有 {len(blocks)} 個遺失區塊，準備補齊...")
        
        for block in blocks:
            start_ms = block['start_time']
            end_ms = block['end_time']
            logging.info(f"  -> 正在抓取區段: {datetime.fromtimestamp(start_ms/1000)} 到 {datetime.fromtimestamp(end_ms/1000)} (共 {block['count']} 筆)")
            
            # Binance 單次最多返回 1500 筆，若區間過大會自動截斷，需分批抓取
            # 這裡為了簡化，使用迴圈直到該區間填滿
            current_start = start_ms
            while current_start <= end_ms:
                try:
                    raw_data = self.client.klines(
                        symbol=symbol, 
                        interval=interval, 
                        startTime=current_start, 
                        endTime=end_ms, 
                        limit=1500
                    )
                    
                    if not raw_data:
                        break
                        
                    # 轉換成 DataFrame
                    columns = ['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 
                               'quote_asset_volume', 'number_of_trades', 'taker_buy_base', 'taker_buy_quote', 'ignore']
                    df_new = pd.DataFrame(raw_data, columns=columns)
                    
                    # 存入資料庫
                    self.db.save_market_data(symbol, interval, df_new)
                    
                    # 更新下一批的起點
                    last_fetched_time = int(df_new['open_time'].max())
                    current_start = last_fetched_time + INTERVAL_MS_MAP.get(interval)
                    
                    time.sleep(0.5) # 避免觸發 API 頻率限制
                    
                except Exception as e:
                    logging.error(f"❌ 抓取 Binance 資料時發生錯誤: {e}")
                    break

    def backfill_external_data(self):
        """ 補齊所有外部數據 """
        logging.info("🔍 檢查並補齊外部數據 (External Data)...")
        
        # 外部數據 API 大多不支援精確的 startTime/endTime
        # 所以我們採取的策略是：如果發現有缺，直接用較大的 limit (例如 1000) 去覆蓋近期歷史
        
        conn = sqlite3.connect(self.db.db_path)
        
        for name, fetcher in self.fetchers.items():
            try:
                # 判定關聯的 Symbol 與 Metric 名稱
                # 假設預設 Metric 就是 name，且 Symbol 通常在 fetcher 內部設定
                metric = name
                symbol = 'QQQ' if name == 'us_stock_qqq' else 'BTCUSDT' # 依照你的架構調整
                
                if name == 'us_stock_qqq':
                    query = f"SELECT open_time FROM market_data WHERE symbol='QQQ'"
                    df = pd.read_sql(query, conn)
                    blocks = self.find_missing_blocks(df, '1d')
                else:
                    query = f"SELECT timestamp as open_time FROM external_data WHERE metric='{metric}'"
                    df = pd.read_sql(query, conn)
                    blocks = self.find_missing_blocks(df, '1h') # 預設外部數據 1h 更新
                
                if blocks:
                    total_missing = sum(b['count'] for b in blocks)
                    logging.warning(f"⚠️ 發現 {name} 遺失大約 {total_missing} 筆，正在重新抓取歷史...")
                    
                    # 計算需要抓幾筆 (至少抓足缺漏數量，並加上安全邊際)
                    fetch_limit = min(total_missing + 50, 1500) 
                    
                    df_ext = fetcher.fetch_data(limit=fetch_limit)
                    
                    if df_ext.empty:
                        continue
                        
                    if name == 'us_stock_qqq':
                        self.db.save_market_data(symbol='QQQ', interval='1d', df=df_ext)
                    else:
                        self.db.save_generic_external_data(df_ext)
                        
                    logging.info(f"✅ 已成功補回 {name} 數據。")
                else:
                    logging.info(f"✅ {name} 資料完整。")
                    
            except Exception as e:
                logging.error(f"❌ 補齊 {name} 時發生錯誤: {e}")
                
        conn.close()

    def run(self):
        print("="*50)
        self.backfill_binance_market_data("BTCUSDT", "1h")
        self.backfill_external_data()
        print("="*50)
        logging.info("🎉 補資料作業完成！")

if __name__ == "__main__":
    backfiller = DataBackfiller()
    backfiller.run()