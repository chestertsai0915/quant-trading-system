import sqlite3
import pandas as pd
from binance.um_futures import UMFutures
import time

# --- 設定 ---
DB_PATH = "trading_data.db"
SYMBOL = "BTCUSDT"  # 預設幣種
COMMISSION_RATE = 0.0005  # 預設手續費率 (萬分之5，可依您的等級修改)

def get_current_price(symbol):
    """ 抓取當前市價 (用於計算未實現損益) """
    try:
        client = UMFutures()
        ticker = client.ticker_price(symbol=symbol)
        return float(ticker['price'])
    except Exception as e:
        print(f" 無法取得最新價格: {e}")
        return None

def analyze_strategy(df, strategy_name, current_price):
    """ 核心損益計算邏輯 (FIFO 先進先出法) """
    
    realized_pnl = 0.0
    total_fees = 0.0
    wins = 0
    losses = 0
    total_trades = 0
    
    # 持倉隊列 [(price, qty), ...]
    position_queue = []
    
    # 確保按時間排序
    df = df.sort_values('timestamp')

    for index, row in df.iterrows():
        side = row['side']
        price = row['price']
        qty = row['quantity']
        # 資料庫若沒存 fee，我們手動估算
        fee = row['fee'] if row['fee'] else (price * qty * COMMISSION_RATE)
        
        total_fees += fee
        
        if side == 'LONG':
            # 開倉：加入隊列
            position_queue.append({'price': price, 'qty': qty})
            
        elif side == 'CLOSE':
            # 平倉：開始從隊列扣除 (FIFO)
            qty_to_close = qty
            trade_pnl = 0
            
            while qty_to_close > 0 and position_queue:
                match = position_queue[0] # 取最早的一筆
                
                if match['qty'] > qty_to_close:
                    # 這筆夠扣，還有剩
                    pnl = (price - match['price']) * qty_to_close
                    match['qty'] -= qty_to_close
                    trade_pnl += pnl
                    qty_to_close = 0
                else:
                    # 這筆不夠扣，全扣完，繼續扣下一筆
                    pnl = (price - match['price']) * match['qty']
                    trade_pnl += pnl
                    qty_to_close -= match['qty']
                    position_queue.pop(0) # 移除這筆
            
            realized_pnl += trade_pnl
            total_trades += 1
            if trade_pnl > 0: wins += 1
            else: losses += 1

    # 計算未實現損益 (剩下的持倉)
    unrealized_pnl = 0.0
    current_qty = 0.0
    avg_entry = 0.0
    
    if position_queue and current_price:
        total_cost = 0
        for pos in position_queue:
            unrealized_pnl += (current_price - pos['price']) * pos['qty']
            current_qty += pos['qty']
            total_cost += pos['price'] * pos['qty']
        
        if current_qty > 0:
            avg_entry = total_cost / current_qty

    # 顯示報告ㄑ
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    net_pnl = realized_pnl + unrealized_pnl - total_fees
    
    print(f"\n{'='*40}")
    print(f" 策略: {strategy_name}")
    print(f"{'='*40}")
    print(f" 總損益 (Net PnL): {net_pnl:.4f} USDT")
    print(f"----------------------------------------")
    print(f" 已實現損益: {realized_pnl:.4f}")
    print(f" 未實現損益: {unrealized_pnl:.4f} (持倉: {current_qty:.3f})")
    print(f" 交易手續費: {total_fees:.4f}")
    print(f"----------------------------------------")
    print(f" 交易次數: {total_trades}")
    print(f" 勝率: {win_rate:.1f}% ({wins}勝 {losses}敗)")
    if current_qty > 0:
        print(f"⚡ 目前持倉均價: {avg_entry:.2f} | 現價: {current_price}")

def main():
    print("正在讀取資料庫...")
    conn = sqlite3.connect(DB_PATH)
    
    # 讀取所有交易
    query = "SELECT * FROM trades ORDER BY timestamp ASC"
    try:
        df = pd.read_sql_query(query, conn)
    except Exception as e:
        print(f" 讀取資料庫失敗: {e}")
        return

    if df.empty:
        print(" 資料庫是空的，還沒有交易紀錄。")
        return

    # 取得最新價格
    current_price = get_current_price(SYMBOL)
    if current_price:
        print(f"🔹 {SYMBOL} 目前市價: {current_price}")

    # 依照策略分組計算
    strategies = df['strategy'].unique()
    
    for strategy in strategies:
        strategy_df = df[df['strategy'] == strategy]
        analyze_strategy(strategy_df, strategy, current_price)

    conn.close()

if __name__ == "__main__":
    main()