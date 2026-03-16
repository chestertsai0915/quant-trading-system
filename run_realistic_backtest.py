import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
import sys
import uuid
import logging
import sqlite3

sys.path.append(os.getcwd())

from utils.config_loader import ConfigLoader
from utils.database import DatabaseHandler
from managers.strategy_manager import StrategyManager
from managers.trade_manager import TradeManager
from managers.data_manager import DataBoard

# ==========================================
# 1. 具備資金與盈虧狀態的動態執行器
# ==========================================
class StatefulBacktestExecutor:
    """ 
    取代原有的 MockExecutor，真實計算手續費、均價與權益變化
    """
    def __init__(self, initial_balance=10000.0, taker_fee=0.0005):
        self.wallet_balance = initial_balance
        self.position = 0.0
        self.avg_price = 0.0
        self.current_price = 0.0
        self.taker_fee = taker_fee
        
    def update_market_price(self, price):
        self.current_price = price

    def get_current_position(self, symbol):
        return self.position

    def get_account_info(self):
        # TradeManager 在第 49 行使用 totalWalletBalance 計算總權益
        unrealized_pnl = 0
        if self.position > 0:
            unrealized_pnl = (self.current_price - self.avg_price) * self.position
        elif self.position < 0:
            unrealized_pnl = (self.avg_price - self.current_price) * abs(self.position)
            
        margin_balance = self.wallet_balance + unrealized_pnl
        
        return {
            'totalWalletBalance': margin_balance,  
            'totalMarginBalance': margin_balance,
            'availableBalance': self.wallet_balance
        }

    def execute_order(self, symbol, side, quantity, reduce_only=False, market_price=None):
        price = market_price if market_price else self.current_price
        if quantity <= 0: return None
        
        notional = quantity * price
        fee = notional * self.taker_fee
        
        # 模擬撮合與 PnL 結算
        if side == 'BUY':
            if self.position < 0: # 平空
                cover_qty = min(quantity, abs(self.position))
                realized_pnl = (self.avg_price - price) * cover_qty
                self.wallet_balance += realized_pnl
                self.position += cover_qty
                if self.position == 0: self.avg_price = 0.0
                
                remain = quantity - cover_qty
                if remain > 0:
                    self.avg_price = price
                    self.position += remain
            else: # 開多
                old_cost = self.position * self.avg_price
                new_cost = quantity * price
                self.avg_price = (old_cost + new_cost) / (self.position + quantity)
                self.position += quantity
                
        elif side == 'SELL':
            if self.position > 0: # 平多
                close_qty = min(quantity, self.position)
                realized_pnl = (price - self.avg_price) * close_qty
                self.wallet_balance += realized_pnl
                self.position -= close_qty
                if self.position == 0: self.avg_price = 0.0
                
                remain = quantity - close_qty
                if remain > 0:
                    self.avg_price = price
                    self.position -= remain
            else: # 開空
                old_cost = abs(self.position) * self.avg_price
                new_cost = quantity * price
                self.avg_price = (old_cost + new_cost) / (abs(self.position) + quantity)
                self.position -= quantity

        self.wallet_balance -= fee # 扣除手續費

        return {
            'orderId': str(uuid.uuid4())[:8],
            'symbol': symbol,
            'status': 'FILLED',
            'executedQty': quantity,
            'side': side
        }
        
    def get_position_details(self, symbol):
        return {'amt': self.position, 'entryPrice': self.avg_price}
        
    def set_leverage(self, symbol, leverage):
        return {'symbol': symbol, 'leverage': leverage}


# ==========================================
# 2. 核心回測引擎 (完美對接實盤類別)
# ==========================================
def run_production_engine_backtest(start_time_str, initial_balance=10000.0, window_size=500):
    logging.getLogger().setLevel(logging.WARNING) # 關閉過多 INFO 避免洗版
    
    print("=== 初始化實盤交易引擎 (回測模式) ===")
    config = ConfigLoader("config.json")
    symbol = config.get("trading", "symbol", "BTCUSDT")
    interval = config.get("trading", "interval", "1h")
    
    # 1. 隔離資料庫 (避免污染實盤 SQLite)
    test_db_path = "backtest_temp.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    # [新增] 傳入 skip_backup=True，避免每次回測都製造無用的啟動備份檔
    db = DatabaseHandler(test_db_path, skip_backup=True)
    
    # 2. 初始化核心 Manager
    strategy_names = config.get('trading', 'strategies', [])
    strategy_manager = StrategyManager(strategy_names)
    
    trade_manager = TradeManager(client=None, db=db, config=config, symbol=symbol, is_paper=True)
    
    # 3. 抽換 Executor 為帶有資金與部位狀態的回測 Executor
    mock_executor = StatefulBacktestExecutor(initial_balance=initial_balance)
    trade_manager.executor = mock_executor
    
    # 4. 準備數據 (改為直接從 trading_data.db 撈取)
    real_db_path = "trading_data.db"
    print(f"從真實資料庫 {real_db_path} 讀取 {symbol} ({interval}) 數據...")
    if not os.path.exists(real_db_path):
        print(f"[錯誤] 找不到真實資料庫 {real_db_path}，請先執行收集數據。")
        return
        
    with sqlite3.connect(real_db_path) as conn:
        query = '''
            SELECT open_time, open, high, low, close, volume 
            FROM market_data 
            WHERE symbol = ? AND interval = ?
            ORDER BY open_time ASC
        '''
        df = pd.read_sql(query, conn, params=(symbol, interval))
        
    if df.empty:
        print(f"[錯誤] 資料庫內沒有 {symbol} {interval} 的數據。")
        return
        
    # 將 DB 裡的 open_time (毫秒) 轉為 datetime
    df['datetime'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.sort_values('datetime').reset_index(drop=True)
    
    start_time = pd.to_datetime(start_time_str)
    try:
        start_idx = df[df['datetime'] >= start_time].index[0]
    except IndexError:
        print(f"[錯誤] 指定時間 {start_time_str} 超出數據庫範圍 (最新時間為 {df['datetime'].iloc[-1]})。")
        return

    equity_curve = []
    print(f"\n開始執行模擬迴圈，從 {start_time_str} 開始，共 {len(df) - start_idx} 筆 K 線...\n")
    
    # 5. 進入 bot.run() 迴圈邏輯
    for i in range(start_idx, len(df)):
        current_time = df['datetime'].iloc[i]
        current_close = df['close'].iloc[i]
        
        # A. 更新市場最新價格給 Executor
        mock_executor.update_market_price(current_close)
        
        # B. 切出目前可見的 K 線 (模擬 DataManager 行為)
        start_slice = max(0, i - window_size + 1)
        kline_slice = df.iloc[start_slice : i+1].copy()
        
        # [模擬] 建構 DataBoard
        data_board = DataBoard(main_kline=kline_slice, external_data={})
        
        # C. 實盤步驟 1: 策略管理器產生訊號
        signals = strategy_manager.generate_signals(data_board)
        
        # D. 實盤步驟 2: 更新 DB 虛擬訊號
        for signal in signals:
            trade_manager.update_virtual_signal(signal)
            
        # E. 實盤步驟 3: 全域調倉
        trade_manager.execute_global_rebalance(current_close)
        
        # F. 記錄權益
        acc_info = mock_executor.get_account_info()
        equity_curve.append({
            'datetime': current_time,
            'equity': acc_info['totalMarginBalance'],
            'price': current_close,
            'position': mock_executor.position
        })
        
        if (i - start_idx) % 1000 == 0:
            print(f"進度: {current_time} | 權益: {acc_info['totalMarginBalance']:.2f} | 總部位: {mock_executor.position:.4f}")

    # ==========================================
    # 結算與繪圖
    # ==========================================
    print("\n=== 回測結束，正在計算績效 ===")
    hist = pd.DataFrame(equity_curve)
    
    if hist.empty:
        print("沒有執行任何回測步驟。")
        return
        
    final_equity = hist['equity'].iloc[-1]
    return_pct = (final_equity - initial_balance) / initial_balance
    max_dd = ((hist['equity'] - hist['equity'].cummax()) / hist['equity'].cummax()).min()
    
    print(f"初始資金: {initial_balance:.2f}")
    print(f"最終資金: {final_equity:.2f}")
    print(f"總報酬率: {return_pct:.2%}")
    print(f"最大回撤: {max_dd:.2%}")
    
    plt.figure(figsize=(14, 8))
    plt.plot(hist['datetime'], hist['equity'], label='Portfolio Equity', color='blue')
    
    benchmark_equity = hist['price'] * (initial_balance / hist['price'].iloc[0])
    plt.plot(hist['datetime'], benchmark_equity, label='Benchmark (Buy & Hold)', color='gray', alpha=0.5)
    
    plt.title("Production Engine Backtest Result")
    plt.xlabel("Date")
    plt.ylabel("Equity (USDT)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig("production_engine_backtest.png")
    print("\n圖表已儲存至 production_engine_backtest.png")
    
    # 清理暫存資料庫
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

if __name__ == "__main__":
    TARGET_START_TIME = "2026-02-10 00:00:00" 
    run_production_engine_backtest(start_time_str=TARGET_START_TIME)