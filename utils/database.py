import os
import shutil
import shutil
import sqlite3
import json
from datetime import datetime
import logging
import pandas as pd 

class DatabaseHandler:
    def __init__(self, db_path="trading_data.db", skip_backup=False):
        self.db_path = db_path
        
        # =建立持久連線，並允許跨執行緒存取
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        
        # 為了保險起見，開啟 WAL 模式 (Write-Ahead Logging)，提升併發讀寫效能
        self.conn.execute("PRAGMA journal_mode=WAL;")
        
        self._init_tables()
        # [修改] 只有當 skip_backup=False 時才備份
        if not skip_backup:
            self._backup_on_startup()
        

    def _init_tables(self):
        """ 初始化資料庫表結構 """
        try:
            cursor = self.conn.cursor()
            
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
                    fee REAL DEFAULT 0,
                    realized_pnl REAL DEFAULT 0
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

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS strategy_states (
                    strategy TEXT PRIMARY KEY,
                    position REAL DEFAULT 0,      
                    entry_price REAL DEFAULT 0,  
                    realized_pnl REAL DEFAULT 0   
                )
            ''')
        
            
            self.conn.commit()
        except Exception as e:
            logging.error(f" [DB ERROR] 初始化資料庫表失敗: {e}")

    def log_trade(self, strategy, symbol, side, price, quantity, order_id, notional, pnl=0):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO trades (timestamp, symbol, strategy, side, price, quantity, notional, order_id, realized_pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (datetime.now(), symbol, strategy, side, price, quantity, notional, order_id, pnl))
            self.conn.commit()
            logging.info(f" [DB] 交易已儲存: {side} {quantity} {symbol} | PnL: {pnl:.2f}")
        except Exception as e:
            logging.error(f" [DB ERROR] 寫入交易失敗: {e}")

    def get_strategy_period_pnl(self, days=30):
        """
        回傳一個字典: {'StrategyA': 500.0, 'StrategyB': -200.0}
        """
        try:
            cursor = self.conn.cursor()
            # SQL 魔法：直接撈出過去 N 天的 PnL 總和
            query = '''
                SELECT strategy, SUM(realized_pnl)
                FROM trades
                WHERE timestamp >= datetime('now', ?)
                GROUP BY strategy
            '''
            # '-30 days'
            time_filter = f'-{days} days'
            cursor.execute(query, (time_filter,))
            
            results = {}
            for row in cursor.fetchall():
                strategy, total_pnl = row
                results[strategy] = total_pnl if total_pnl else 0.0
                
            return results
            
        except Exception as e:
            logging.error(f"[DB Error] 查詢區間損益失敗: {e}")
            return {}

    def log_signal(self, strategy, symbol, action, price, reason):
        """ 紀錄策略訊號 """
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO signals (timestamp, strategy, symbol, action, signal_price, reason)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (datetime.now(), strategy, symbol, action, price, reason))
            self.conn.commit()
            
        except Exception as e:
            logging.error(f" [DB ERROR] 寫入訊號失敗: {e}")

    def log_snapshot(self, balance, unrealized_pnl, btc_price, positions):
        """ 紀錄資產快照 """
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO snapshots (timestamp, total_balance, unrealized_pnl, btc_price, positions_json)
                VALUES (?, ?, ?, ?, ?)
            ''', (datetime.now(), balance, unrealized_pnl, btc_price, json.dumps(positions)))
            self.conn.commit()
            
        except Exception as e:
            logging.error(f" [DB ERROR] 寫入快照失敗: {e}")

    # 新增：儲存 K 線數據 (批量寫入)
    def save_market_data(self, symbol, interval, df):
        if df.empty: return

        try:
            cursor = self.conn.cursor()
            df_to_save = df.copy()
            # 將 DataFrame 轉為 list of tuples，準備寫入
            # 假設 df 的欄位順序是: open_time, open, high, low, close, volume, close_time
            # (這取決於你的 DataLoader 怎麼整理，這裡做個防呆處理)
            # 3. 欄位名稱標準化 (Mapping)
            # 你的 DataLoader 可能把時間叫做 'timestamp', 'date', 'Date', 'index' 等等
            # 我們統一改成 'open_time'
            if 'open_time' not in df_to_save.columns:
                rename_map = {
                    'timestamp': 'open_time',
                    'Date': 'open_time',
                    'date': 'open_time',
                    'index': 'open_time',
                    'Close time': 'close_time'
                }
                df_to_save.rename(columns=rename_map, inplace=True)
            else:
                # 即使有 open_time，也要確保 close_time 被正確更名
                if 'Close time' in df_to_save.columns:
                    df_to_save.rename(columns={'Close time': 'close_time'}, inplace=True)
            

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

            self.conn.commit()
            
            
        except Exception as e:
            logging.error(f"[DB ERROR] 寫入市場數據失敗: {e}")

    #  新增：讀取 K 線數據 (給策略用)
    def load_market_data(self, symbol, interval, limit=200):
        """ 讀取 K 線數據 """
        try:
            
            query = f'''
                SELECT open_time, open, high, low, close, volume, close_time
                FROM market_data
                WHERE symbol = ? AND interval = ?
                ORDER BY open_time DESC
                LIMIT ?
            '''
            
            df = pd.read_sql(query, self.conn, params=(symbol, interval, limit))
            
            if df.empty:
                return pd.DataFrame()

            # 排序回來 (ASC)
            df = df.sort_values('open_time').reset_index(drop=True)
            
            # 確保數值型別
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
        
            cursor= self.conn.cursor()
            
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

            self.conn.commit()
            
            
        except Exception as e:
            logging.error(f" [DB ERROR] 儲存通用外部數據失敗: {e}")

    # 新增：讀取外部數據
    def load_external_data(self, symbol, metric, start_time=None, limit=200):
        """ 讀取外部數據 (對齊版) """
        try:
            cursor = self.conn.cursor()
            
            if start_time is not None:
                # 找 start_time 之前的最新一筆
                query_prev = '''
                    SELECT MAX(timestamp) 
                    FROM external_data
                    WHERE symbol = ? AND metric = ? AND timestamp < ?
                '''
                cursor.execute(query_prev, (symbol, metric, start_time))
                result = cursor.fetchone()
                
                actual_start_time = result[0] if result and result[0] is not None else start_time
                
                query = '''
                    SELECT timestamp as open_time, value 
                    FROM external_data
                    WHERE symbol = ? AND metric = ? AND timestamp >= ?
                    ORDER BY timestamp ASC
                '''
                df = pd.read_sql(query, self.conn, params=(symbol, metric, actual_start_time))
            
            else:
                query = '''
                    SELECT timestamp as open_time, value 
                    FROM external_data
                    WHERE symbol = ? AND metric = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                '''
                df = pd.read_sql(query, self.conn, params=(symbol, metric, limit))
            
            if not df.empty:
                df = df.sort_values('open_time').reset_index(drop=True)
                
            return df
            
        except Exception as e:
            logging.error(f" [DB ERROR] 讀取外部數據失敗: {e}")
            return pd.DataFrame()
    
    def get_strategy_position(self, strategy_name, symbol):
        """
        查詢特定策略目前的持倉狀態
        回傳: (quantity, avg_price) 如果沒持倉則回傳 (0, 0)
        """
        query = """
        SELECT side, quantity, price 
        FROM trades 
        WHERE strategy = ? AND symbol = ? 
        ORDER BY timestamp DESC 
        LIMIT 1
        """
        try:
            # 使用我們剛才建立的 self.conn
            cursor = self.conn.cursor()
            cursor.execute(query, (strategy_name, symbol))
            row = cursor.fetchone()
            
            if row:
                side, qty, price = row
                # 如果最後動作是 LONG，代表現在持有這個數量的倉位
                if side == 'LONG':
                    return float(qty), float(price)
            
            return 0.0, 0.0
            
        except Exception as e:
            logging.error(f"[DB Error] 查詢策略持倉失敗: {e}")
            return 0.0, 0.0
        
    def close(self):
        if self.conn:
            self.conn.close()

    def _backup_on_startup(self):
        try:
            if not os.path.exists(self.db_path):
                return

            backup_dir = "backups_startup"
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)

            # 檔名加上 startup 標記
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(backup_dir, f"startup_backup_{timestamp}.db")
            
            # 使用 shutil 複製 (啟動當下通常還沒連線，直接複製是安全的)
            shutil.copy2(self.db_path, backup_file)
            print(f"[Backup] 啟動前備份完成: {backup_file}")
            
            # 簡單清理邏輯 (只留最近 3 個啟動備份)
            files = sorted(
                [os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.endswith('.db')],
                key=os.path.getmtime
            )
            while len(files) > 3:
                os.remove(files.pop(0)) # 刪除最舊的
                
        except Exception as e:
            print(f"[Backup Error] 啟動備份失敗: {e}")

    def get_strategy_state(self, strategy):
        """ [單純讀取] """
        cursor = self.conn.cursor()
        cursor.execute("SELECT position, entry_price, realized_pnl FROM strategy_states WHERE strategy=?", (strategy,))
        row = cursor.fetchone()
        if row:
            return row[0], row[1], row[2]
        return 0.0, 0.0, 0.0

    def save_strategy_state(self, strategy, position, entry_price, realized_pnl):
        """ [單純寫入] 不做任何計算，給什麼存什麼 """
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO strategy_states (strategy, position, entry_price, realized_pnl)
                VALUES (?, ?, ?, ?)
            ''', (strategy, position, entry_price, realized_pnl))
            self.conn.commit()
        except Exception as e:
            logging.error(f"[DB Error] 儲存策略狀態失敗: {e}")

    def get_daily_pnl_history(self, days=30):
        """
        取得過去 N 天，每個策略的「每日損益」數據 (用於計算 Sharpe)
        回傳格式: { 'StrategyA': [10, -5, 20...], 'StrategyB': [...] }
        """
        try:
            cursor = self.conn.cursor()
            # SQL: 按日期和策略分組，加總 realized_pnl
            query = '''
                SELECT 
                    strategy,
                    DATE(timestamp) as trade_date, 
                    SUM(realized_pnl) as daily_pnl
                FROM trades
                WHERE timestamp >= datetime('now', ?)
                GROUP BY strategy, trade_date
                ORDER BY trade_date ASC
            '''
            time_filter = f'-{days} days'
            cursor.execute(query, (time_filter,))
            
            history = {}
            for row in cursor.fetchall():
                strat, date, pnl = row
                if strat not in history:
                    history[strat] = []
                history[strat].append(pnl)
                
            return history
        except Exception as e:
            logging.error(f"[DB Error] 查詢每日損益失敗: {e}")
            return {}
        
    def get_all_virtual_positions(self):
        """
        回傳: {'StrategyA': 1.0, 'StrategyB': -1.0, 'StrategyC': 0.0}
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT strategy, position FROM strategy_states")
            rows = cursor.fetchall()
            return {row[0]: row[1] for row in rows}
        except Exception as e:
            logging.error(f"[DB Error] 批量讀取策略狀態失敗: {e}")
            return {}