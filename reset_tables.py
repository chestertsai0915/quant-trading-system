import sqlite3
import os

db_path = 'trading_data.db'

print(f" 準備重置表格結構 (保留市場數據)...")

if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 定義要 "徹底銷毀" 的舊表格
        # 注意：我們不刪除 market_data 和 external_data
        tables_to_drop = [
            'trades',           # 舊的交易表 (缺欄位)
            'signals',          # 訊號表
            'snapshots',        # 資產快照
            'strategy_states'   # 策略狀態
        ]

        for table in tables_to_drop:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
            print(f" -> 已刪除舊表格: {table}")
        
        conn.commit()
        conn.close()
        print(" 重置完成！請重啟機器人，它會自動重建包含 realized_pnl 的新表格。")
        
    except Exception as e:
        print(f" 資料庫錯誤: {e}")
else:
    print(" 資料庫不存在，無需重置。")