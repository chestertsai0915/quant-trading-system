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
        
       

        # 4. 🔥 新增：市場數據表 (Market Data)
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
            for _, row in df_to_save.iterrows():

                raw_open_time = row['open_time']
                if hasattr(raw_open_time, 'timestamp'):
                    # 如果是 Timestamp 物件 -> 轉成毫秒 (整數)
                    open_time_val = int(raw_open_time.timestamp() * 1000)
                else:
                    # 如果原本就是數字 -> 直接轉 int
                    open_time_val = int(raw_open_time)

                # 🔥 處理 close_time (同理)
                close_time_val = 0
                if 'close_time' in row:
                    raw_close_time = row['close_time']
                    if hasattr(raw_close_time, 'timestamp'):
                        close_time_val = int(raw_close_time.timestamp() * 1000)
                    else:
                        close_time_val = int(raw_close_time)

                data_to_insert.append((
                    symbol,
                    interval,
                    open_time_val,
                    float(row['open']),
                    float(row['high']),
                    float(row['low']),
                    float(row['close']),
                    float(row['vol']),
                    close_time_val
                ))

            # 使用 INSERT OR REPLACE 來處理重複數據 (更新舊的，插入新的)
            cursor.executemany('''
                INSERT OR REPLACE INTO market_data 
                (symbol, interval, open_time, open, high, low, close, volume, close_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', data_to_insert)

            conn.commit()
            conn.close()
            # logging.info(f"💾 [DB] 已儲存 {len(df)} 筆 K 線數據") 
            # (這行建議註解掉，不然 log 會太吵)
            
        except Exception as e:
            logging.error(f"[DB ERROR] 寫入市場數據失敗: {e}")

    # 👇 新增：讀取 K 線數據 (給策略用)
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