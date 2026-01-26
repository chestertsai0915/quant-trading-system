import sqlite3
import json
from datetime import datetime
import logging

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