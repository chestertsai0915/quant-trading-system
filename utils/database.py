import sqlite3
import json
from datetime import datetime
import logging
import pandas as pd 

class DatabaseHandler:
    def __init__(self, db_name="trading_data.db"):
        self.db_name = db_name
        self._init_tables()

    def _connect(self):
        return sqlite3.connect(self.db_name)

    def _init_tables(self):
        """ 初始化資料庫表結構 """
        conn = self._connect()
        cursor = conn.cursor()
        
        # 1. 交易紀錄表 (Trades)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                symbol TEXT,
                strategy TEXT,
                side TEXT,
                price REAL,
                quantity REAL,
                notional REAL,
                order_id TEXT,
                fee REAL DEFAULT 0
            )
        ''')

        # 2. 訊號紀錄表 (Signals) - 用於分析策略準度
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                strategy TEXT,
                symbol TEXT,
                action TEXT,
                signal_price REAL,
                reason TEXT
            )
        ''')

        # 3. 資產快照表 (Snapshots) - 用於畫資金曲線
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                total_balance REAL,
                unrealized_pnl REAL,
                btc_price REAL,
                positions_json TEXT
            )
        ''')
        
       

        # 4. 市場數據表 (Market Data)
        # 使用複合主鍵 (symbol + interval + open_time) 確保唯一性
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS market_data (
                symbol TEXT,
                interval TEXT,
                open_time INTEGER,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                close_time INTEGER,
                PRIMARY KEY (symbol, interval, open_time)
            )
        ''')
        
        # 5. 新增外部數據表 (External Data)
        # 設計成通用格式 (Generic Schema)，任何數據都能存
        # metric: 數據名稱 (e.g., 'funding_rate', 'long_short_ratio', 'fear_greed')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS external_data (
                timestamp INTEGER,
                symbol TEXT,
                metric TEXT,
                value REAL,
                PRIMARY KEY (timestamp, symbol, metric)
            )
        ''')
        
        conn.commit()
        conn.close()

    def log_trade(self, strategy, symbol, side, price, quantity, order_id, notional):
        """ 紀錄一筆成交 """
        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO trades (timestamp, symbol, strategy, side, price, quantity, notional, order_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (datetime.now(), symbol, strategy, side, price, quantity, notional, order_id))
            conn.commit()
            conn.close()
            logging.info(f" [DB] 交易已儲存: {side} {quantity} {symbol}")
        except Exception as e:
            logging.error(f" [DB ERROR] 寫入交易失敗: {e}")

    def log_signal(self, strategy, symbol, action, price, reason):
        """ 紀錄策略訊號 """
        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO signals (timestamp, strategy, symbol, action, signal_price, reason)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (datetime.now(), strategy, symbol, action, price, reason))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f" [DB ERROR] 寫入訊號失敗: {e}")

    def log_snapshot(self, balance, unrealized_pnl, btc_price, positions):
        """ 紀錄資產快照 """
        try:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO snapshots (timestamp, total_balance, unrealized_pnl, btc_price, positions_json)
                VALUES (?, ?, ?, ?, ?)
            ''', (datetime.now(), balance, unrealized_pnl, btc_price, json.dumps(positions)))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f" [DB ERROR] 寫入快照失敗: {e}")

    # 新增：儲存 K 線數據 (批量寫入)
    def save_market_data(self, symbol, interval, df):
        if df.empty: return

        try:
            conn = self._connect()
            cursor = conn.cursor()
            df_to_save = df.copy()
            # 將 DataFrame 轉為 list of tuples，準備寫入
            # 假設 df 的欄位順序是: open_time, open, high, low, close, volume, close_time
            # (這取決於你的 DataLoader 怎麼整理，這裡做個防呆處理)
            # 3. 欄位名稱標準化 (Mapping)
            # 你的 DataLoader 可能把時間叫做 'timestamp', 'date', 'Date', 'index' 等等
            # 我們統一改成 'open_time'
            rename_map = {
                'timestamp': 'open_time',
                'Date': 'open_time',
                'date': 'open_time',
                'index': 'open_time',
                'Close time': 'close_time' # 有些 loader 會這樣命名
            }
            df_to_save.rename(columns=rename_map, inplace=True)

            data_to_insert = []

            if pd.api.types.is_numeric_dtype(df_to_save['open_time']):
                df_to_save['open_time'] = pd.to_datetime(df_to_save['open_time'], unit='ms')
            # 確保 open_time 是 datetime 型態
            if not pd.api.types.is_datetime64_any_dtype(df_to_save['open_time']):
                df_to_save['open_time'] = pd.to_datetime(df_to_save['open_time'])

            # 將 datetime64[ns] (奈秒) 轉成 int64 (奈秒)，再除以 1,000,000 變成 毫秒
            #這行指令會瞬間把整欄轉成乾淨的整數 (int)
            df_to_save['open_time'] = df_to_save['open_time'].astype('int64') // 10**6

            # 處理 close_time (如果有)
            if 'close_time' in df_to_save.columns:
                 if pd.api.types.is_numeric_dtype(df_to_save['close_time']):
                     df_to_save['close_time'] = pd.to_datetime(df_to_save['close_time'], unit='ms')
                 if not pd.api.types.is_datetime64_any_dtype(df_to_save['close_time']):
                    df_to_save['close_time'] = pd.to_datetime(df_to_save['close_time'])
                 df_to_save['close_time'] = df_to_save['close_time'].astype('int64') // 10**6
            else:
                df_to_save['close_time'] = 0

                data_to_insert = list(df_to_save[[
                'open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time'
            ]].itertuples(index=False, name=None))
            
            # 注意：這裡的 tuple 順序要跟 data_to_insert 欄位順序一樣
            # 我們需要把 symbol, interval 加進去
            final_data = []
            for row in data_to_insert:
                # row 內容: (open_time, open, high, low, close, volume, close_time)
                # 我們要加上 symbol 和 interval
                final_data.append((symbol, interval) + row)

            cursor.executemany('''
                INSERT OR REPLACE INTO market_data 
                (symbol, interval, open_time, open, high, low, close, volume, close_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', final_data)

            conn.commit()
            conn.close()
            
        except Exception as e:
            logging.error(f"[DB ERROR] 寫入市場數據失敗: {e}")

    #  新增：讀取 K 線數據 (給策略用)
    def load_market_data(self, symbol, interval, limit=200):
        try:
            conn = self._connect()
            
            # 讀取最近的 N 筆數據
            query = f'''
                SELECT open_time, open, high, low, close, volume, close_time
                FROM market_data
                WHERE symbol = ? AND interval = ?
                ORDER BY open_time DESC
                LIMIT ?
            '''
            
            df = pd.read_sql(query, conn, params=(symbol, interval, limit))
            conn.close()
            
            if df.empty:
                return pd.DataFrame()

            # 排序回來 (因為 SQL 是 DESC，為了策略運算我們要由舊到新 ASC)
            df = df.sort_values('open_time').reset_index(drop=True)
            
            # 確保型別正確 (從 DB 讀出來有時會跑掉)
            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            df[numeric_cols] = df[numeric_cols].astype(float)
            
            return df
            
        except Exception as e:
            logging.error(f" [DB ERROR] 讀取市場數據失敗: {e}")
            return pd.DataFrame()
        
    #  新增：儲存外部數據的方法
    def save_generic_external_data(self, df):
        """
        通用的儲存函數
        df 必須包含: ['open_time', 'symbol', 'metric', 'value']
        """
        if df.empty: return

        try:
            conn = self._connect()
            cursor = conn.cursor()
            
            # 確保型態正確
            # 時間轉 int
            if not pd.api.types.is_integer_dtype(df['open_time']):
                 # 如果是 timestamp object
                if pd.api.types.is_datetime64_any_dtype(df['open_time']):
                     df['open_time'] = df['open_time'].astype('int64') // 10**6
                else:
                     # 如果是 float 或 string
                     df['open_time'] = df['open_time'].astype('int64')

            # 準備數據 (轉成 list of tuples)
            # 注意順序要對應 SQL
            data_to_insert = list(df[['open_time', 'symbol', 'metric', 'value']].itertuples(index=False, name=None))

            cursor.executemany('''
                INSERT OR REPLACE INTO external_data 
                (timestamp, symbol, metric, value)
                VALUES (?, ?, ?, ?)
            ''', data_to_insert)

            conn.commit()
            conn.close()
            
        except Exception as e:
            logging.error(f" [DB ERROR] 儲存通用外部數據失敗: {e}")

    # 新增：讀取外部數據
    def load_external_data(self, symbol, metric, start_time=None, limit=200):
        """
        讀取外部數據 (智慧對齊版)
        :param start_time: K 線的起始時間。函數會自動抓取該時間點「前一筆」數據，確保 merge_asof 在第一行就有值。
        """
        try:
            conn = self._connect()
            cursor = conn.cursor()
            
            if start_time is not None:
                # --- 步驟 1: 尋找「前一筆」的時間點 ---
                # 我們不盲目減去固定時間，而是精準找出「比 start_time 小的最新一筆數據」是何時
                query_prev = '''
                    SELECT MAX(timestamp) 
                    FROM external_data
                    WHERE symbol = ? AND metric = ? AND timestamp < ?
                '''
                cursor.execute(query_prev, (symbol, metric, start_time))
                result = cursor.fetchone()
                
                # 如果找得到前一筆，我們就從那一筆的時間開始抓 (包含那一筆)
                # 如果找不到 (代表 start_time 之前完全沒數據)，就維持原本的 start_time
                actual_start_time = result[0] if result and result[0] is not None else start_time
                
                # --- 步驟 2: 抓取範圍內的數據 ---
                query = '''
                    SELECT timestamp as open_time, value 
                    FROM external_data
                    WHERE symbol = ? AND metric = ? AND timestamp >= ?
                    ORDER BY timestamp ASC
                '''
                df = pd.read_sql(query, conn, params=(symbol, metric, actual_start_time))
            
            else:
                # 模式 B: 簡單模式 (Legacy Mode) - 只抓最新的 N 筆
                query = '''
                    SELECT timestamp as open_time, value 
                    FROM external_data
                    WHERE symbol = ? AND metric = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                '''
                df = pd.read_sql(query, conn, params=(symbol, metric, limit))
            
            conn.close()
            
            if not df.empty:
                # 確保按時間由舊到新排序
                df = df.sort_values('open_time').reset_index(drop=True)
                
            return df
            
        except Exception as e:
            logging.error(f" [DB ERROR] 讀取外部數據失敗: {e}")
            return pd.DataFrame()