import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import importlib.util
import sys
import os
import argparse

# 引用模組
sys.path.append(os.getcwd())
try:
    from backtesting.pure_engine import PureBacktestEngine
    from backtesting.data_factory import BacktestDataFactory # 新增引用
except ImportError as e:
    print(f"[Error] 模組引用失敗: {e}")
    sys.exit(1)

# ... (calculate_metrics 和 plot_performance 函式保持不變，為了節省篇幅省略，請保留原有的) ...
# 請將原本 brain.py 中的 calculate_metrics 和 plot_performance 複製貼上回來這裡
# ==========================================
# 1. 績效計算與繪圖工具 (平台底層)
# ==========================================
def calculate_metrics(history_df, initial_balance=10000):
    if history_df.empty: return {}
    equity = history_df['equity']
    final_balance = equity.iloc[-1]
    total_return = (final_balance - initial_balance) / initial_balance
    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max
    max_dd = drawdown.min()
    pct_change = equity.pct_change().dropna()
    sharpe = 0
    if pct_change.std() != 0:
        sharpe = (pct_change.mean() / pct_change.std()) * np.sqrt(365 * 24)
    return {
        "Return": total_return, "MaxDD": max_dd, "Sharpe": sharpe, "Final": final_balance
    }

def plot_performance(df_full, hist_is, hist_os, split_date, strategy_name):
    # (請填入原本的繪圖程式碼，完全不用改)
    plt.style.use('ggplot')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
    full_time = pd.to_datetime(df_full['datetime'])
    benchmark = df_full['close'] * (10000 / df_full['close'].iloc[0])
    ax1.plot(full_time, benchmark, color='gray', alpha=0.3, label='Benchmark (BTC)')
    if not hist_is.empty:
        t_is = pd.to_datetime(hist_is['datetime'])
        ax1.plot(t_is, hist_is['equity'], label='In-Sample (Train)', color='#1f77b4', linewidth=1.5)
    if not hist_os.empty:
        t_os = pd.to_datetime(hist_os['datetime'])
        ax1.plot(t_os, hist_os['equity'], label='Out-Sample (Test)', color='#ff7f0e', linewidth=1.5)
    ax1.axvline(pd.to_datetime(split_date), color='red', linestyle='--', alpha=0.6, label='Split Date')
    ax1.set_title(f'Strategy: {strategy_name}', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Equity (USDT)')
    ax1.legend(loc='upper left')
    full_hist = pd.concat([hist_is, hist_os]).drop_duplicates(subset=['datetime']).sort_values('datetime')
    if not full_hist.empty:
        full_hist['datetime'] = pd.to_datetime(full_hist['datetime'])
        rolling_max = full_hist['equity'].cummax()
        dd = (full_hist['equity'] - rolling_max) / rolling_max
        ax2.fill_between(full_hist['datetime'], dd, 0, color='#d62728', alpha=0.3)
        ax2.plot(full_hist['datetime'], dd, color='#d62728', linewidth=1)
    ax2.set_ylabel('Drawdown')
    import matplotlib.ticker as mtick
    ax2.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    output_file = f"report_{strategy_name}.png"
    plt.tight_layout()
    plt.savefig(output_file)
    print(f"\n[BRAIN] 圖表已生成: {output_file}")


# ==========================================
# 2. 動態載入策略
# ==========================================
def load_strategy_from_file(filepath):
    """ 回傳: (run_func, requirements_list, strategy_name) """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"找不到檔案: {filepath}")
        
    module_name = os.path.basename(filepath).replace(".py", "")
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    if not hasattr(module, 'run'):
        raise ValueError("策略檔案中必須包含 'def run(row, account):' 函式！")
    
    # 嘗試讀取 requirements，若無則回傳空 list
    reqs = getattr(module, 'requirements', [])
        
    return module.run, reqs, module_name

# ==========================================
# 3. 模擬器主程序
# ==========================================
def main():
    parser = argparse.ArgumentParser(description='WorldQuant Brain Style Simulator')
    parser.add_argument('strategy_file', type=str, help='Path to your strategy file')
    args = parser.parse_args()

    # 1. 載入策略與需求
    try:
        strategy_func, requirements, strategy_name = load_strategy_from_file(args.strategy_file)
        print(f"[BRAIN] 成功載入策略: {strategy_name}")
        print(f"[BRAIN] 策略需求特徵: {requirements}")
    except Exception as e:
        print(f"[Error] 載入策略失敗: {e}")
        return

    # 2. 呼叫 Factory 準備數據 (取代讀取 CSV)
    # 這裡預設回測 BTCUSDT 1h，你也可以改成從 args 讀入
    symbol = "BTCUSDT"
    interval = "1h"
    
    try:
        factory = BacktestDataFactory() # 會連線 DB
        # [關鍵] 傳入 requirements 給 Factory
        df = factory.prepare_features(symbol, interval, feature_ids=requirements)
    except Exception as e:
        print(f"[Error] 數據準備失敗: {e}")
        return

    # 自動切分 IS/OS
    target_split = pd.to_datetime("2025-06-01")
    if df['datetime'].max() < target_split:
        split_idx = int(len(df) * 0.7)
        SPLIT_DATE = df['datetime'].iloc[split_idx]
        print(f"[BRAIN] 數據長度不足，自動調整切分點至: {SPLIT_DATE}")
    else:
        SPLIT_DATE = target_split

    # 3. 執行全域回測
    print("--- 執行全域回測 ---")
    engine = PureBacktestEngine(df, initial_balance=10000)
    engine.run(strategy_func)
    
    full_hist = pd.DataFrame(engine.account.equity_curve)
    
    # 切分結果
    hist_is = full_hist[full_hist['datetime'] < SPLIT_DATE].copy()
    hist_os = full_hist[full_hist['datetime'] >= SPLIT_DATE].copy()

    # 4. 顯示績效
    if not hist_is.empty:
        m_is = calculate_metrics(hist_is, initial_balance=10000)
        print(f"IS | Return: {m_is.get('Return', 0):.2%} | Sharpe: {m_is.get('Sharpe', 0):.2f}")
    
    if not hist_os.empty:
        os_start_balance = hist_os['equity'].iloc[0]
        m_os = calculate_metrics(hist_os, initial_balance=os_start_balance)
        print(f"OS | Return: {m_os.get('Return', 0):.2%} | Sharpe: {m_os.get('Sharpe', 0):.2f}")

    # 5. 繪圖
    plot_performance(df, hist_is, hist_os, SPLIT_DATE, strategy_name)

if __name__ == "__main__":
    main()