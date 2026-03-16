import sqlite3
import pandas as pd
from datetime import datetime

# 設定
DB_PATH = "trading_data.db"

# 時框轉毫秒映射
INTERVAL_MS_MAP = {
    "1m": 60 * 1000,
    "5m": 5 * 60 * 1000,
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def check_integrity(df, name, interval, time_col='open_time'):
    if df.empty:
        print(f"--- [{name}] 沒有資料 ---")
        return

    # 取得起點與終點
    first_time = df[time_col].min()
    ms_per_interval = INTERVAL_MS_MAP.get(interval, 3600000) # 預設 1h
    
    # 對齊現在時間
    now_ms = int(datetime.now().timestamp() * 1000)
    last_theoretical_time = (now_ms // ms_per_interval) * ms_per_interval

    # 建立理論時間軸
    expected_times = range(first_time, last_theoretical_time + ms_per_interval, ms_per_interval)
    expected_df = pd.DataFrame({time_col: expected_times})

    # 比對
    missing = expected_df[~expected_df[time_col].isin(df[time_col])]
    
    status = "✅ 完整" if missing.empty else f"❌ 遺失 {len(missing)} 筆"
    print(f"[{name: <15}] 區間: {interval} | 狀態: {status}")
    
    if not missing.empty and len(missing) <= 5:
        missing_list = [datetime.fromtimestamp(t/1000).strftime('%Y-%m-%d %H:%M') for t in missing[time_col]]
        print(f"    -> 遺失點: {missing_list}")

def main():
    conn = get_db_connection()
    
    print(f"開始檢查資料庫: {DB_PATH}\n" + "="*50)

    # 1. 檢查 market_data (幣安與 QQQ)
    try:
        # 找出所有不同的 symbol/interval 組合
        md_list = pd.read_sql("SELECT DISTINCT symbol, interval FROM market_data", conn)
        for _, row in md_list.iterrows():
            s, i = row['symbol'], row['interval']
            df = pd.read_sql(f"SELECT open_time FROM market_data WHERE symbol='{s}' AND interval='{i}'", conn)
            check_integrity(df, f"Market:{s}", i)
    except Exception as e:
        print(f"讀取 market_data 失敗: {e}")

    # 2. 檢查 external_data (Funding Rate, FearGreed 等)
    try:
        # 找出所有不同的 metric
        ext_list = pd.read_sql("SELECT DISTINCT symbol, metric FROM external_data", conn)
        for _, row in ext_list.iterrows():
            s, m = row['symbol'], row['metric']
            df = pd.read_sql(f"SELECT timestamp FROM external_data WHERE symbol='{s}' AND metric='{m}'", conn)
            
            # 根據 DataCollector 的邏輯判斷時框
            # 外部數據通常是 1h 更新一次
            check_integrity(df, f"Ext:{m}", "1h", time_col='timestamp')
    except Exception as e:
        print(f"讀取 external_data 失敗: {e}")

    conn.close()
    print("="*50 + "\n檢查結束")

if __name__ == "__main__":
    main()