import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
import sys

# 確保能引用到 backtesting 資料夾
sys.path.append(os.getcwd())
from backtesting.pure_engine import PureBacktestEngine

# ==========================================
# 1. 策略邏輯轉換 (Class -> Function)
# ==========================================
def price_volume_strategy(row, account):
    """
    對應 PriceVolume1 的邏輯
    """
    # --- A. 參數設定 (寫死或從外部閉包傳入) ---
    mad_ma = 10
    win = 25
    th1 = 0.8
    th2 = 0.9
    
    # --- B. 定義特徵欄位名稱 (必須與 CSV 欄位一致) ---
    fid_mad     = f"mad_close_{mad_ma}_v1"
    fid_bs      = "bs_ratio_v1"
    fid_mad_th  = f"mad_quantile_{mad_ma}_{win}_{th1}_v1"
    fid_bs_th   = f"bs_quantile_{win}_{th2}_v1"
    fid_time    = "is_us_trade_time_v1"

    # --- C. 從 row 取值 (防呆處理) ---
    try:
        curr_mad    = row[fid_mad]
        curr_bs     = row[fid_bs]
        curr_mad_th = row[fid_mad_th]
        curr_bs_th  = row[fid_bs_th]
        is_trade    = bool(row[fid_time])
    except KeyError as e:
        # 如果 CSV 缺欄位，印出錯誤並跳過
        print(f"[Error] 缺少欄位: {e}")
        return 'HOLD', 0

    # --- D. 交易邏輯 ---
    
    # 進場條件
    # 注意：這裡邏輯是 "同時" 大於閾值
    long_condition = (curr_mad > curr_mad_th) and \
                     (curr_bs > curr_bs_th) and \
                     (is_trade)

    # 出場條件
    # 注意：這裡邏輯是 "任一" 低於閾值就跑
    exit_condition = ((curr_mad < curr_mad_th) or (curr_bs < curr_bs_th)) and \
                     (is_trade)

    # --- E. 發出訊號 ---
    if long_condition:
        # 如果目前空手，買入 100% (All-in)
        # 原本策略是 quantity=0.005，但回測引擎通常用資金比例
        if account.position == 0:
            return 'BUY', 1
        
            
    elif exit_condition:
        # 如果有持倉，清倉
        if account.position > 0:
            return 'SELL', 1.0

    return 'HOLD', 0

# ==========================================
# 2. 績效計算工具
# ==========================================
def calculate_metrics(history_df, initial_balance=10000):
    if history_df.empty:
        return {}
    
    # 權益曲線
    equity = history_df['equity']
    
    # 1. 總報酬
    final_balance = equity.iloc[-1]
    total_return = (final_balance - initial_balance) / initial_balance
    
    # 2. 最大回撤 (MDD)
    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max
    max_dd = drawdown.min()
    
    # 3. 夏普比率 (假設無風險利率為 0, 數據為小時級別 -> 年化需 * sqrt(365*24))
    # 計算每筆變動的百分比
    pct_change = equity.pct_change().dropna()
    if pct_change.std() == 0:
        sharpe = 0
    else:
        sharpe = (pct_change.mean() / pct_change.std()) * np.sqrt(365 * 24)
    
    # 4. 交易次數與勝率 (需要解析 trade history，這裡暫時用簡單估算)
    # PureEngine 沒有直接回傳 trade list，我們看 equity 變動次數
    # 這邊簡單回傳核心指標
    
    return {
        "Initial": f"{initial_balance:.2f}",
        "Final": f"{final_balance:.2f}",
        "Return": f"{total_return:.2%}",
        "Max Drawdown": f"{max_dd:.2%}",
        "Sharpe Ratio": f"{sharpe:.2f}"
    }

# ==========================================
# 3. 主程式
# ==========================================
def main():
    csv_path = 'backtesting_data.csv'
    if not os.path.exists(csv_path):
        print(f"錯誤：找不到 {csv_path}，請先執行 data_factory 產生數據。")
        return

    # 1. 讀取數據
    print(f"正在讀取 {csv_path}...")
    df = pd.read_csv(csv_path)
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.sort_values('datetime').reset_index(drop=True)
    
    print(f"總數據量: {len(df)} 筆 | 時間範圍: {df['datetime'].iloc[0]} -> {df['datetime'].iloc[-1]}")

    
    engine = PureBacktestEngine(df, initial_balance=10000)
    engine.run(price_volume_strategy)
    hist = pd.DataFrame(engine.account.equity_curve)
    metrics = calculate_metrics(hist)
    print("結果:", metrics)

    # 5. 繪圖比較
    plt.figure(figsize=(14, 8))

    # 畫 IS
    if not hist.empty:
        plt.plot(pd.to_datetime(hist['datetime']), hist['equity'], label='Equity', color='blue')

    # 畫 Benchmark (BTC Buy & Hold) - 用全域數據畫
    full_time = pd.to_datetime(df['datetime'])
    first_price = df['close'].iloc[0]
    benchmark = df['close'] * (10000 / first_price)
    plt.plot(full_time, benchmark, label='Benchmark (BTC)', color='gray', alpha=0.3)

    plt.title(f"Strategy Backtest")
    plt.xlabel("Date")
    plt.ylabel("Equity (USDT)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    # 儲存
    plt.savefig("backtest_is_os_result.png")
    print("\n[SYSTEM] 圖表已儲存至 backtest_is_os_result.png")
    # plt.show()

if __name__ == "__main__":
    main()