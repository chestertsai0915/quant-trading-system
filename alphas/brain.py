import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import importlib.util
import sys
import os
import argparse
from scipy import stats  # 用於 T 檢定

# 引用模組
sys.path.append(os.getcwd())
try:
    from backtesting.pure_engine import PureBacktestEngine
    from backtesting.data_factory import BacktestDataFactory
except ImportError as e:
    print(f"[Error] 模組引用失敗: {e}")
    sys.exit(1)

# ==========================================
# 1. 進階績效計算 (核心邏輯)
# ==========================================
class PerformanceAnalyzer:
    def __init__(self, history_df, benchmark_series):
        """
        :param history_df: 包含 datetime, equity, position 的 DataFrame
        :param benchmark_series: 基準價格序列 (Series), index需為 datetime
        """
        self.hist = history_df.copy()
        self.hist.set_index('datetime', inplace=True)
        self.benchmark = benchmark_series.copy()
        
        # [修復] 這裡計算的 returns 只存在 self.hist，不會影響外部傳進來的 df
        self.hist['returns'] = self.hist['equity'].pct_change().fillna(0)
        
        # 對齊基準收益率
        self.benchmark_returns = self.benchmark.pct_change().reindex(self.hist.index).fillna(0)
        
    def get_basic_metrics(self):
        if self.hist.empty: return {}
        total_ret = (self.hist['equity'].iloc[-1] / self.hist['equity'].iloc[0]) - 1
        
        # MDD
        roll_max = self.hist['equity'].cummax()
        dd = (self.hist['equity'] - roll_max) / roll_max
        max_dd = dd.min()
        
        # 年化 Sharpe
        freq_factor = 24 * 365
        if len(self.hist) > 1:
            time_diff = (self.hist.index[1] - self.hist.index[0]).total_seconds()
            if time_diff > 0:
                freq_factor = (365 * 24 * 3600) / time_diff

        std = self.hist['returns'].std()
        sharpe = 0
        if std != 0:
            sharpe = (self.hist['returns'].mean() / std) * np.sqrt(freq_factor)
            
        return {
            "Total Return": total_ret,
            "Max Drawdown": max_dd,
            "Sharpe Ratio": sharpe,
            "Vol (Ann.)": std * np.sqrt(freq_factor)
        }

    def get_advanced_metrics(self):
        if self.hist.empty: return {}
        # 1. IC (Information Coefficient)
        pos = self.hist['position']
        future_ret = self.benchmark_returns.shift(-1)
        
        valid_data = pd.DataFrame({'pos': pos, 'ret': future_ret}).dropna()
        if not valid_data.empty and valid_data['pos'].std() != 0:
            ic_pearson = valid_data['pos'].corr(valid_data['ret'], method='pearson')
            ic_spearman = valid_data['pos'].corr(valid_data['ret'], method='spearman')
        else:
            ic_pearson = 0
            ic_spearman = 0

        # 2. IR (Information Ratio)
        active_ret = self.hist['returns'] - self.benchmark_returns
        tracking_error = active_ret.std()
        ir = 0
        if tracking_error != 0:
            ir = (active_ret.mean() / tracking_error) * np.sqrt(24*365)

        # 3. Sharpe Stability
        window = 24 * 30 
        rolling_mean = self.hist['returns'].rolling(window).mean()
        rolling_std = self.hist['returns'].rolling(window).std()
        rolling_sharpe = (rolling_mean / rolling_std) * np.sqrt(24*365)
        sharpe_stability = rolling_sharpe.std()

        return {
            "IC (Pearson)": ic_pearson,
            "IC (Spearman)": ic_spearman,
            "IR": ir,
            "Sharpe Stability": sharpe_stability
        }

def perform_ttest(is_returns, os_returns):
    """ Welch's t-test """
    if len(is_returns) < 2 or len(os_returns) < 2:
        return np.nan, np.nan, "數據不足"

    # 檢定 H1: IS Mean > OS Mean (衰退)
    t_stat, p_value_2tail = stats.ttest_ind(is_returns, os_returns, equal_var=False, alternative='greater')
    
    result_text = "無顯著差異 (Pass)"
    if p_value_2tail < 0.05:
        result_text = "⚠️ 顯著衰退 (Significant Decay)"
    elif p_value_2tail < 0.1:
        result_text = "⚠️ 輕微衰退 (Potential Decay)"
    
    return t_stat, p_value_2tail, result_text

# ==========================================
# 2. 報告產生器 (寫入檔案版)
# ==========================================
def save_report_to_file(df_full, hist_is, hist_os, split_date, strategy_name):
    filename = f"report_{strategy_name}.txt"
    
    # 計算 returns 用於 T-test (修復 KeyError 的關鍵)
    # 這裡直接操作 series，不依賴 PerformanceAnalyzer 的內部狀態
    is_rets = hist_is.set_index('datetime')['equity'].pct_change().dropna()
    os_rets = hist_os.set_index('datetime')['equity'].pct_change().dropna()

    benchmark_series = df_full.set_index('datetime')['close']

    # 準備分析器
    analyzer_is = PerformanceAnalyzer(hist_is, benchmark_series)
    basic_is = analyzer_is.get_basic_metrics()
    adv_is = analyzer_is.get_advanced_metrics()

    has_os = not hist_os.empty
    if has_os:
        analyzer_os = PerformanceAnalyzer(hist_os, benchmark_series)
        basic_os = analyzer_os.get_basic_metrics()
        adv_os = analyzer_os.get_advanced_metrics()

    with open(filename, "w", encoding="utf-8") as f:
        def w(text=""): 
            f.write(text + "\n")

        w("="*60)
        w(f"{'★ QUANT BRAIN 完整回測報告 ★':^56}")
        w("="*60)
        w(f"策略名稱: {strategy_name}")
        w(f"回測時間: {df_full['datetime'].min()} ~ {df_full['datetime'].max()}")
        w(f"切割日期: {split_date}")
        w("-" * 60)

        # --- In-Sample ---
        w(f"\n[{'In-Sample (訓練集)':^20}]")
        w(f"  Return: {basic_is.get('Total Return', 0):>8.2%} | Sharpe: {basic_is.get('Sharpe Ratio', 0):>6.2f} | MaxDD: {basic_is.get('Max Drawdown', 0):>7.2%}")
        w(f"  IC(Sp): {adv_is.get('IC (Spearman)', 0):>8.4f} | IR: {adv_is.get('IR', 0):>10.4f} | Stability: {adv_is.get('Sharpe Stability', 0):>6.2f}")

        # --- Out-Sample ---
        w(f"\n[{'Out-Sample (測試集)':^20}]")
        if has_os:
            w(f"  Return: {basic_os.get('Total Return', 0):>8.2%} | Sharpe: {basic_os.get('Sharpe Ratio', 0):>6.2f} | MaxDD: {basic_os.get('Max Drawdown', 0):>7.2%}")
            w(f"  IC(Sp): {adv_os.get('IC (Spearman)', 0):>8.4f} | IR: {adv_os.get('IR', 0):>10.4f} | Stability: {adv_os.get('Sharpe Stability', 0):>6.2f}")
        else:
            w("  (無 OS 數據)")

        # --- Robustness Check ---
        w("\n" + "-"*60)
        w(f"{'過擬合檢定 (Robustness Check)':^56}")
        w("-"*60)

        if has_os:
            # 1. T-Test
            t_stat, p_val, res_text = perform_ttest(is_rets, os_rets)
            w(f"1. 收益率分佈檢定 (T-Test):")
            w(f"   T-Stat: {t_stat:.4f} (IS Mean - OS Mean)")
            w(f"   P-Value: {p_val:.4f}")
            w(f"   >> 結論: {res_text}")

            # 2. Sharpe Decay
            sharpe_is = basic_is.get('Sharpe Ratio', 0)
            sharpe_os = basic_os.get('Sharpe Ratio', 0)
            
            w(f"\n2. Sharpe 變動:")
            w(f"   IS: {sharpe_is:.2f} -> OS: {sharpe_os:.2f}")
            
            if sharpe_is > 0:
                decay = (sharpe_os - sharpe_is) / sharpe_is
                w(f"   衰退率: {decay:.2%}")
                if decay < -0.5: w("   >> 警告: Sharpe 衰退嚴重 (>50%)")
            
            # 3. IC Check
            ic_is = adv_is.get('IC (Spearman)', 0)
            ic_os = adv_os.get('IC (Spearman)', 0)
            w(f"\n3. 預測力 (IC) 變動:")
            w(f"   IS: {ic_is:.4f} -> OS: {ic_os:.4f}")
            if ic_os < 0.01: w("   >> 警告: OS IC 接近 0 或負值，預測失效")

        else:
            w("無法執行檢定 (缺 OS 數據)")

        w("="*60)

    print(f"[BRAIN] 文字報告已儲存至: {filename}")

def plot_performance_advanced(df_full, hist_is, hist_os, split_date, strategy_name):
    # 保持原樣，這會生成圖片
    plt.style.use('ggplot')
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 12), sharex=True, gridspec_kw={'height_ratios': [3, 1, 1]})
    
    full_time = pd.to_datetime(df_full['datetime'])
    benchmark = df_full['close'] * (10000 / df_full['close'].iloc[0])
    ax1.plot(full_time, benchmark, color='gray', alpha=0.3, label='Benchmark (BTC)')

    if not hist_is.empty:
        ax1.plot(pd.to_datetime(hist_is['datetime']), hist_is['equity'], label='IS Equity', color='#1f77b4')
    if not hist_os.empty:
        ax1.plot(pd.to_datetime(hist_os['datetime']), hist_os['equity'], label='OS Equity', color='#ff7f0e')

    ax1.axvline(pd.to_datetime(split_date), color='red', linestyle='--', alpha=0.6, label='Split Date')
    ax1.set_title(f'Strategy: {strategy_name}', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Equity')
    ax1.legend(loc='upper left')

    # Rolling Sharpe
    full_hist = pd.concat([hist_is, hist_os]).drop_duplicates(subset=['datetime']).sort_values('datetime')
    if not full_hist.empty:
        full_hist.set_index('datetime', inplace=True)
        full_hist['returns'] = full_hist['equity'].pct_change()
        
        window = 24 * 30 
        roll_mean = full_hist['returns'].rolling(window).mean()
        roll_std = full_hist['returns'].rolling(window).std()
        roll_sharpe = (roll_mean / roll_std) * np.sqrt(24*365)
        
        ax2.plot(roll_sharpe.index, roll_sharpe, color='purple', linewidth=1, label='Rolling Sharpe (30D)')
        ax2.axhline(0, color='black', linewidth=0.5, linestyle='--')
        ax2.axvline(pd.to_datetime(split_date), color='red', linestyle='--', alpha=0.3)
        ax2.set_ylabel('Sharpe')
        ax2.legend(loc='upper left')

        # Drawdown
        roll_max = full_hist['equity'].cummax()
        dd = (full_hist['equity'] - roll_max) / roll_max
        ax3.fill_between(dd.index, dd, 0, color='#d62728', alpha=0.3, label='Drawdown')
        ax3.set_ylabel('DD')
        ax3.legend(loc='lower left')
        
        import matplotlib.ticker as mtick
        ax3.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))

    plt.tight_layout()
    output_file = f"report_{strategy_name}.png"
    plt.savefig(output_file)
    print(f"[BRAIN] 圖表報告已儲存至: {output_file}")

# ==========================================
# 3. 主流程
# ==========================================
def load_strategy_from_file(filepath):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"找不到檔案: {filepath}")
    module_name = os.path.basename(filepath).replace(".py", "")
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, 'run'):
        raise ValueError("策略檔案必須包含 'def run(row, account):'")
    reqs = getattr(module, 'requirements', [])
    return module.run, reqs, module_name

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('strategy_file', type=str)
    args = parser.parse_args()

    # 1. 載入策略
    try:
        strategy_func, requirements, strategy_name = load_strategy_from_file(args.strategy_file)
        print(f"[BRAIN] 載入策略: {strategy_name}")
    except Exception as e:
        print(f"[Error] {e}")
        return

    # 2. 準備數據
    try:
        factory = BacktestDataFactory() # skip_backup=True
        df = factory.prepare_features("BTCUSDT", "1h", feature_ids=requirements)
    except Exception as e:
        print(f"[Error] 數據準備失敗: {e}")
        return

    # 切分點
    target_split = pd.to_datetime("2025-06-01")
    if df['datetime'].max() < target_split:
        split_idx = int(len(df) * 0.7)
        SPLIT_DATE = df['datetime'].iloc[split_idx]
        print(f"[BRAIN] 自動調整切分點: {SPLIT_DATE}")
    else:
        SPLIT_DATE = target_split

    # 3. 執行全域回測
    print("--- 執行全域回測 ---")
    engine = PureBacktestEngine(df, initial_balance=10000)
    engine.run(strategy_func)
    
    full_hist = pd.DataFrame(engine.account.equity_curve)
    
    if full_hist.empty:
        print("[Error] 回測結果為空")
        return

    hist_is = full_hist[full_hist['datetime'] < SPLIT_DATE].copy()
    hist_os = full_hist[full_hist['datetime'] >= SPLIT_DATE].copy()

    # 4. 生成報告 (檔案版)
    save_report_to_file(df, hist_is, hist_os, SPLIT_DATE, strategy_name)
    
    # 5. 繪圖
    plot_performance_advanced(df, hist_is, hist_os, SPLIT_DATE, strategy_name)

if __name__ == "__main__":
    main()