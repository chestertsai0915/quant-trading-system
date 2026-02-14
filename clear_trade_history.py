import sqlite3
import os

db_path = 'trading_data.db'
json_path = 'portfolio_state.json'

print(f" 準備清除交易紀錄，但保留 K 線數據...")

if not os.path.exists(db_path):
    print(" 資料庫檔案不存在！")
    exit()

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. 定義要清除的表格 (只清交易相關，保留 market_data, external_data)
    tables_to_clear = [
        'trades',           # 交易歷史
        'signals',          # 訊號歷史
        'snapshots',        # 資產快照
        'strategy_states'   # 策略持倉狀態 (重要！這會重置策略持倉為 0)
    ]

    for table in tables_to_clear:
        # 檢查表格是否存在
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
        if cursor.fetchone():
            print(f" -> 正在清空 {table} ...")
            cursor.execute(f"DELETE FROM {table}")
            # 重置自增 ID (id 歸零)
            try:
                cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}'")
            except:
                pass # 有些表可能沒有自增 ID，忽略錯誤
        else:
            print(f" -> {table} 不存在，跳過。")

    conn.commit()
    
    # 執行 VACUUM 釋放空間 (選用)
    print(" -> 正在重組資料庫 (VACUUM)...")
    cursor.execute("VACUUM")
    
    conn.close()
    print(" 資料庫交易紀錄已清空！")

    # 2. 連動處理：刪除 portfolio_state.json
    # 因為 DB 空了，舊的權重狀態也該重置，否則會導致邏輯錯亂
    if os.path.exists(json_path):
        os.remove(json_path)
        print(f" 已刪除 {json_path} (觸發重新初始化)")
    else:
        print(f" -> {json_path} 不存在，無需刪除。")

    print("\n 完成！現在您可以重新啟動機器人，它會以「全新狀態」開始交易。")

except Exception as e:
    print(f" 發生錯誤: {e}")