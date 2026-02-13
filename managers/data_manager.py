from datetime import datetime
import logging
import threading
import pandas as pd
import time
from data_sources.registry import get_all_fetchers
from data_loader import DataLoader
from features.feature_engineer import FeatureEngineer

# --- 新增：數據儀表板 (Data Transfer Object) ---
class DataBoard:
    """
    數據儀表板：
    負責將「不同頻率」的數據封裝在一起傳遞給策略。
    原則：
    1. 不在這裡做 merge (Scale Separation)。
    2. 提供原始數據供策略層自由取用。
    """
    def __init__(self, main_kline: pd.DataFrame, external_data: dict):
        self.main_kline = main_kline        # 高頻主數據 (如 BTC 1h)
        self.external_data = external_data  # 低頻數據字典 (如 QQQ, FearGreed...)

    def get_latest_state(self, source_name: str, col_name: str = None):
        """
        查詢低頻數據的「最新狀態」 (Regime Filter 用)
        """
        df = self.external_data.get(source_name)
        if df is None or df.empty:
            return None
        
        # 取最後一筆 (代表最新已知的狀態)
        latest = df.iloc[-1]
        
        if col_name:
            return latest.get(col_name)
        return latest

class DataManager:
    def __init__(self, client, db, symbol, interval):
        self.client = client
        self.db = db
        self.symbol = symbol
        self.interval = interval
        self.loader = DataLoader(self.client, self.db)
        self.fetchers = get_all_fetchers()
        self.last_processed_time = 0
        self._external_cache = {}  # Key: source_name, Value: latest_record (dict)
        # --- 多尺度架構修改 ---
        # 獨立存儲各個尺度的數據，不進行合併
        self._cache_lock = threading.Lock()
        self._external_data_store = {} # Key: source_name, Value: DataFrame
        
        self.feature_engineer = FeatureEngineer()
        self._is_running = True
        
        self._auto_backfill()
        self._start_background_scheduler()
        logging.info(f"載入外部數據源: {list(self.fetchers.keys())}")

    def get_history_klines(self, limit=1500):
        return self.loader.get_binance_klines(self.symbol, self.interval, limit=limit)

    def check_new_candle(self):
        """ 偵測新 K 線 """
        raw_df = self.loader.get_binance_klines(self.symbol, self.interval, limit=2)
        if raw_df.empty:
            return False, 0, None

        latest_closed_kline = raw_df.iloc[-2]
        closed_time = int(latest_closed_kline['open_time'])

        if closed_time > self.last_processed_time:
            return True, closed_time, raw_df.iloc[:-1]
        
        return False, 0, None

    def _start_background_scheduler(self):
        thread = threading.Thread(target=self._update_cache_worker, daemon=True)
        thread.start()
        logging.info(" 外部數據背景更新啟動") 

    def _update_cache_worker(self):
        """ 
        背景更新：各自獨立維護不同頻率的數據 (Scale Separation)
        """
        while self._is_running:
            logging.info("[BG-TASK] 開始更新外部數據...")
            
            for name, fetcher in self.fetchers.items():
                try:
                    df = fetcher.fetch_data()
                    if df is None or df.empty: continue

                    
                    if name == 'us_stock_qqq':
                        self.db.save_market_data(symbol='QQQ', interval='1d', df=df)
                    else:
                        self.db.save_generic_external_data(df)
 
                    # C. 更新記憶體快取 (In-Memory Cache)
                        # 取最新的一筆資料放入快取
                        latest_record = df.iloc[-1].to_dict()
                        with self._cache_lock:
                            self._external_cache[name] = latest_record 
                except Exception as e:
                    logging.error(f"[BG-TASK] 更新失敗 {name}: {e}")

            time.sleep(3600) 
    def get_cached_external_data(self):
        """ 主程式呼叫這個方法，0 秒取得數據  """
        with self._cache_lock:
            return self._external_cache.copy()
        
    def update_etl_process(self, closed_time, df_to_save):
        """ 
        ETL 流程:是打包 DataBoard
        """
        logging.info(f"[ETL] 處理新 K 線: {pd.to_datetime(closed_time, unit='ms')}")
        
        # 1. 存入最新的 K 線
        self.db.save_market_data(self.symbol, self.interval, df_to_save)
        
        # 2. 讀取主頻率數據 (High Freq)
        main_df = self.db.load_market_data(self.symbol, self.interval, limit=1500)
        
        # 3. 計算 Start Time (用於撈取對應範圍的外部數據)
        start_time = None
        if not main_df.empty:
            # 取主 K 線的第一筆時間作為起點
            start_time = int(main_df['open_time'].min())
        
        # 4. 準備外部低頻數據 (Low Freq) - 從 DB 讀取
        external_snapshot = self._load_all_external_data_from_db(start_time=start_time)

        # 5. 打包成 DataBoard
        data_board = DataBoard(main_kline=main_df, external_data=external_snapshot)
        
        self.last_processed_time = closed_time
        return data_board

    def _load_all_external_data_from_db(self, start_time=None):
        """
        從資料庫載入所有已註冊的外部數據
        參數:
          start_time: 指定要撈取的起始時間 (通常是 main_df 的開始時間)
        """
        snapshot = {}
        # 如果沒給 start_time，就用 limit 兜底
        default_limit = 1000 
        
        # 定義 Source -> Metrics 的映射 (因為 DB 查詢需要 metric 名稱)
        # 這裡建議把所有可能的 metric 都列出來
        metrics_map = {
            'fear_greed': ['fear_greed'],
            'funding_rate': ['funding_rate'],
            'google_trends': ['google_trends_BTC', 'google_trends_crypto', 'google_trends_Bitcoin'],
            'fred_macro': ['yield_10y', 'yield_2y', 'fed_assets']
        }

        for source_name in self.fetchers.keys():
            try:
                # Case 1: 美股 QQQ (存放在 market_data 表)
                # load_market_data 目前只支援 limit，不支援 start_time，所以維持原樣或給大一點的 limit
                if source_name == 'us_stock_qqq':
                    df = self.db.load_market_data('QQQ', '1d', limit=500)
                    if not df.empty:
                        snapshot[source_name] = df
                    continue

                # Case 2: 通用外部數據 (存放在 external_data 表)
                target_metrics = metrics_map.get(source_name)
                if not target_metrics:
                    continue

                dfs = []
                for metric in target_metrics:
                    # 決定 symbol (Funding Rate 用幣種，其他用 GLOBAL)
                    target_symbol = self.symbol if source_name == 'funding_rate' else 'GLOBAL'
                    
                    # 呼叫 database.py 的 load_external_data
                    # 這裡會用到它原本的邏輯：如果有 start_time，就用時間篩選；否則用 limit
                    df = self.db.load_external_data(
                        symbol=target_symbol, 
                        metric=metric, 
                        start_time=start_time, # <--- 傳入 main_df 的第一根時間
                        limit=default_limit
                    )
                    
                    if not df.empty:
                        # [關鍵修正] database.py 回傳的 df 沒有 'metric' 欄位，手動補上
                        # 這樣後續 FeatureEngineer 才能識別
                        df['metric'] = metric
                        dfs.append(df)
                
                if dfs:
                    # 合併並排序
                    merged_df = pd.concat(dfs, ignore_index=True).sort_values('open_time')
                    snapshot[source_name] = merged_df
                
            except Exception as e:
                logging.error(f"[ETL] 從 DB 讀取 {source_name} 失敗: {e}")
        
        return snapshot
        
    def _auto_backfill(self):
        """
        [自動回補機制]
        1. 查詢 DB 最後一筆 K 線時間
        2. 取得現在 UTC 時間
        3. 計算時間差 -> 換算成缺少的 K 線數量 (Limit)
        4. 精準回補
        """
        logging.info(f"[BACKFILL] 正在檢查 {self.symbol} 數據完整性...")
        
        try:
            # 1. 取得 DB 裡最新的一筆 K 線
            last_df = self.db.load_market_data(self.symbol, self.interval, limit=1)
            
            fetch_limit = 1000 # 預設值 (如果是全新的 DB)

            if not last_df.empty:
                last_time_ms = int(last_df.iloc[-1]['open_time'])
                current_time_ms = int(time.time() * 1000)
                
                # 2. 計算時間差 (毫秒)
                time_diff = current_time_ms - last_time_ms
                
                # 3. 解析週期 (將 '1h', '15m' 轉為毫秒)
                interval_ms = self._get_interval_ms(self.interval)
                
                if interval_ms > 0:
                    # 算出缺了幾根 (無條件捨去)
                    missing_candles = time_diff // interval_ms
                    
                    # 加一點緩衝 (Buffer) 確保最後一根未收盤的也能更新
                    fetch_limit = int(missing_candles) + 2
                    
                    logging.info(f"[BACKFILL] 上次收盤: {pd.to_datetime(last_time_ms, unit='ms')} | "
                                 f"現在時間: {pd.to_datetime(current_time_ms, unit='ms')} | "
                                 f"缺少 K 線: {missing_candles} 根")
                else:
                    logging.warning(f"[BACKFILL] 無法解析週期 {self.interval}，使用預設值 1000")
            
            else:
                logging.info("[BACKFILL] 資料庫為空，執行初始化下載 (1000根)...")

            # 4. 執行回補 (設定上限以免 API 報錯)
            # 幣安單次最多 1000 或 1500，我們保險設 1000
            if fetch_limit > 1000:
                fetch_limit = 1000
                logging.warning("[BACKFILL] 缺失數據超過 1000 根，僅回補最近 1000 根。")
            
            if fetch_limit > 0:
                logging.info(f"[BACKFILL] 開始回補 {fetch_limit} 根 K 線...")
                df = self.loader.get_binance_klines(self.symbol, self.interval, limit=fetch_limit)
                
                if not df.empty:
                    self.db.save_market_data(self.symbol, self.interval, df)
                    logging.info(f"[BACKFILL] 成功寫入 {len(df)} 筆數據！斷層修復完成。")
                else:
                    logging.warning("[BACKFILL] 幣安 API 回傳空數據。")
            else:
                logging.info("[BACKFILL] 數據已是最新，無需回補。")

        except Exception as e:
            logging.error(f"[BACKFILL ERROR] 自動回補失敗: {e}")


    def _get_interval_ms(self, interval):
        mapping = {'1h': 3600000, '4h': 14400000, '15m': 900000, '1d': 86400000}
        return mapping.get(interval, 3600000)