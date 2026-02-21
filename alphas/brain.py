import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import importlib.util
import sys
import os
import argparse
from scipy import stats  # 引入統計模組

# 引用模組
sys.path.append(os.getcwd())
try:
    from backtesting.pure_engine import PureBacktestEngine
    from backtesting.data_factory import BacktestDataFactory
except ImportError as e:
    print(f"[Error] 模組引用失敗: {e}")
    sys.exit(1)



# 1. 統計檢定工具箱 (Statistical Tools)

def test_sharpe_difference(rets_is, rets_os):
    """
    檢定 Sharpe Ratio 是否顯著衰退
    H0: SR_is <= SR_os
    H1: SR_is > SR_os (衰退)
    Reference: Lo (2002), The Statistics of Sharpe Ratios
    """
    n_is, n_os = len(rets_is), len(rets_os)
    if n_is < 2 or n_os < 2: return np.nan, np.nan, "N/A"

    # 計算 Sharpe (未年化，因為統計檢定用單期即可)
    mean_is, std_is = rets_is.mean(), rets_is.std()
    mean_os, std_os = rets_os.mean(), rets_os.std()
    
    if std_is == 0 or std_os == 0: return np.nan, np.nan, "Std=0"

    sr_is = mean_is / std_is
    sr_os = mean_os / std_os

    # 計算 Sharpe 的變異數近似值
    # Var(SR) approx (1 + 0.5 * SR^2) / N
    var_is = (1 + 0.5 * sr_is**2) / n_is
    var_os = (1 + 0.5 * sr_os**2) / n_os

    # Z-Test
    diff = sr_is - sr_os
    std_diff = np.sqrt(var_is + var_os)
    z_score = diff / std_diff
    
    # 單尾檢定 (我們只在意 IS > OS 的情況)
    p_value = 1 - stats.norm.cdf(z_score)
    
    result = " 無顯著差異"
    if p_value < 0.05: result = " 顯著衰退 (Significant)"
    elif p_value < 0.1: result = " 疑似衰退 (Potential)"

    return z_score, p_value, result

def test_correlation_difference(r_is, n_is, r_os, n_os):
    """
    檢定 IC (相關係數) 是否顯著衰退 (Fisher Z Transformation)
    H0: Corr_is <= Corr_os
    H1: Corr_is > Corr_os
    """
    if n_is < 4 or n_os < 4: return np.nan, np.nan, "N/A"
    
    # Fisher Z 轉換 (處理 r=1 或 r=-1 的邊界情況)
    r_is = np.clip(r_is, -0.999, 0.999)
    r_os = np.clip(r_os, -0.999, 0.999)

    z_is = 0.5 * np.log((1 + r_is) / (1 - r_is))
    z_os = 0.5 * np.log((1 + r_os) / (1 - r_os))

    # 標準誤
    se = np.sqrt(1/(n_is-3) + 1/(n_os-3))

    # Z-Score
    z_stat = (z_is - z_os) / se
    p_value = 1 - stats.norm.cdf(z_stat)

    result = " 無顯著差異"
    if p_value < 0.05: result = " 顯著衰退 (Significant)"
    elif p_value < 0.1: result = " 疑似衰退 (Potential)"

    return z_stat, p_value, result



# 2. 進階績效計算

class PerformanceAnalyzer:
    def __init__(self, history_df, benchmark_series):
        self.hist = history_df.copy()
        self.hist.set_index('datetime', inplace=True)
        self.benchmark = benchmark_series.copy()
        
        # 基礎報酬率
        self.hist['returns'] = self.hist['equity'].pct_change().fillna(0)
        self.benchmark_returns = self.benchmark.pct_change().reindex(self.hist.index).fillna(0)
        
        # 超額報酬 (Active Return) -> 用於算 IR
        self.hist['active_returns'] = self.hist['returns'] - self.benchmark_returns

    def get_basic_metrics(self):
        if self.hist.empty: return {}
        total_ret = (self.hist['equity'].iloc[-1] / self.hist['equity'].iloc[0]) - 1
        
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
        # IC
        pos = self.hist['position']
        future_ret = self.benchmark_returns.shift(-1)
        valid = pd.DataFrame({'pos': pos, 'ret': future_ret}).dropna()
        
        ic_sp = 0
        if not valid.empty and valid['pos'].std() != 0:
            ic_sp = valid['pos'].corr(valid['ret'], method='spearman')

        # IR (Information Ratio)
        active_ret = self.hist['active_returns']
        tracking_err = active_ret.std()
        ir = 0
        if tracking_err != 0:
            ir = (active_ret.mean() / tracking_err) * np.sqrt(24*365)

        return {
            "IC (Spearman)": ic_sp,
            "IR": ir,
            "n_samples": len(valid) # 用於 IC 檢定
        }



# 3. 完整健檢邏輯 

def perform_robustness_check(hist_is, hist_os, benchmark_series):
    """
    執行完整的衰退檢定 (Return, Sharpe, IC, IR, Volatility)
    """
    results = {}
    
    # 建立 Analyzer 以取得運算所需的數據
    analyzer_is = PerformanceAnalyzer(hist_is, benchmark_series)
    analyzer_os = PerformanceAnalyzer(hist_os, benchmark_series)
    
    adv_is = analyzer_is.get_advanced_metrics()
    adv_os = analyzer_os.get_advanced_metrics()

    # 取得原始序列 (Series)
    rets_is = analyzer_is.hist['returns']
    rets_os = analyzer_os.hist['returns']
    active_is = analyzer_is.hist['active_returns']
    active_os = analyzer_os.hist['active_returns']

    if len(rets_is) < 10 or len(rets_os) < 10:
        return {"error": "數據不足"}

    # --- 1. 收益率檢定 (T-Test) ---
    t_stat, p_val_mean = stats.ttest_ind(rets_is, rets_os, equal_var=False, alternative='greater')
    mean_res = " 通過"
    if p_val_mean < 0.05: mean_res = " 顯著衰退"
    results['return'] = {'stat': t_stat, 'p': p_val_mean, 'res': mean_res, 'name': '收益率 (Return)'}

    # --- 2. 波動率檢定 (Levene Test) ---
    stat_var, p_val_var = stats.levene(rets_is, rets_os, center='median')
    is_std, os_std = rets_is.std(), rets_os.std()
    var_res = " 通過"
    if p_val_var < 0.05 and os_std > is_std: var_res = " 風險顯著擴大"
    results['volatility'] = {'stat': stat_var, 'p': p_val_var, 'res': var_res, 'name': '波動率 (Volatility)'}

    # --- 3. Sharpe 衰退檢定 (Lo's Statistic) ---
    z_shp, p_shp, res_shp = test_sharpe_difference(rets_is, rets_os)
    results['sharpe'] = {'stat': z_shp, 'p': p_shp, 'res': res_shp, 'name': '夏普值 (Sharpe)'}

    # --- 4. IR 衰退檢定 (同 Sharpe 邏輯，但用 Active Returns) ---
    z_ir, p_ir, res_ir = test_sharpe_difference(active_is, active_os)
    results['ir'] = {'stat': z_ir, 'p': p_ir, 'res': res_ir, 'name': '資訊率 (IR)'}

    # --- 5. IC 衰退檢定 (Fisher Z) ---
    ic_is = adv_is.get('IC (Spearman)', 0)
    ic_os = adv_os.get('IC (Spearman)', 0)
    n_is = adv_is.get('n_samples', 0)
    n_os = adv_os.get('n_samples', 0)
    
    z_ic, p_ic, res_ic = test_correlation_difference(ic_is, n_is, ic_os, n_os)
    results['ic'] = {'stat': z_ic, 'p': p_ic, 'res': res_ic, 'name': '預測力 (IC)'}

    return results


# 4. 報告與繪圖

def save_report_to_file(df_full, hist_is, hist_os, split_date, strategy_name):
    filename = f"report_{strategy_name}.txt"
    benchmark_series = df_full.set_index('datetime')['close']

    # 計算基礎指標
    analyzer_is = PerformanceAnalyzer(hist_is, benchmark_series)
    basic_is = analyzer_is.get_basic_metrics()
    adv_is = analyzer_is.get_advanced_metrics()

    has_os = not hist_os.empty
    if has_os:
        analyzer_os = PerformanceAnalyzer(hist_os, benchmark_series)
        basic_os = analyzer_os.get_basic_metrics()
        adv_os = analyzer_os.get_advanced_metrics()
        
        checks = perform_robustness_check(hist_is, hist_os, benchmark_series)

    with open(filename, "w", encoding="utf-8") as f:
        def w(text=""): f.write(text + "\n")

        w("="*60)
        w(f"{' QUANT BRAIN 全方位體檢報告 ':^56}")
        w("="*60)
        w(f"策略代號: {strategy_name}")
        w(f"樣本切割: {split_date}")
        w("-" * 60)

        # --- 1. 數據對比 ---
        w(f"\n【數據對比 (Metrics Comparison)】")
        headers = f"{'Metric':<12} | {'IS (Train)':<12} | {'OS (Test)':<12} | {'Delta':<10}"
        w(headers)
        w("-" * 55)
        
        if has_os:
            # 輔助函式：安全取值
            def get_fmt(dic, key, is_pct=False):
                val = dic.get(key, 0)
                return f"{val:>12.2%}" if is_pct else f"{val:>12.4f}"
            
            w(f"{'Return':<12} | {get_fmt(basic_is, 'Total Return', True)} | {get_fmt(basic_os, 'Total Return', True)} |")
            w(f"{'Sharpe':<12} | {get_fmt(basic_is, 'Sharpe Ratio')} | {get_fmt(basic_os, 'Sharpe Ratio')} |")
            w(f"{'IC (Sp)':<12} | {get_fmt(adv_is, 'IC (Spearman)')} | {get_fmt(adv_os, 'IC (Spearman)')} |")
            w(f"{'IR':<12} | {get_fmt(adv_is, 'IR')} | {get_fmt(adv_os, 'IR')} |")
            w(f"{'MaxDD':<12} | {get_fmt(basic_is, 'Max Drawdown', True)} | {get_fmt(basic_os, 'Max Drawdown', True)} |")
        else:
            w("  (無 OS 數據)")

        # --- 2. 統計檢定結果 ---
        w("\n" + "="*60)
        w(f"{' 統計衰退檢定 (Statistical Decay Tests) ':^56}")
        w("="*60)
        w("檢定假設 H0: 策略在 OS 的表現 <= IS (無顯著衰退)")
        w("P-Value < 0.05 代表拒絕 H0 -> 確認發生顯著衰退\n")

        if has_os and "error" not in checks:
            # 遍歷所有檢定項目
            test_order = ['return', 'volatility', 'sharpe', 'ic', 'ir']
            
            for key in test_order:
                item = checks.get(key)
                if not item: continue
                
                w(f"[{item['name']}]")
                w(f"   結果: {item['res']}")
                w(f"   數據: Stat={item['stat']:.4f}, P-Value={item['p']:.4f}")
                
                # 針對特定結果加註解
                if item['p'] < 0.05:
                    w("   >> 警告: 統計上顯著變差")
                w("-" * 30)

        else:
            w("  (無法執行檢定)")

        w("="*60)

    print(f"[BRAIN] 完整體檢報告已儲存至: {filename}")

def plot_performance_advanced(df_full, hist_is, hist_os, split_date, strategy_name):
   
    plt.style.use('ggplot')
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 12), sharex=True, gridspec_kw={'height_ratios': [3, 1, 1]})
    
    full_time = pd.to_datetime(df_full['datetime'])
    
    if not hist_is.empty:
        ax1.plot(pd.to_datetime(hist_is['datetime']), hist_is['equity'], label='IS Equity', color='#1f77b4')
    if not hist_os.empty:
        ax1.plot(pd.to_datetime(hist_os['datetime']), hist_os['equity'], label='OS Equity', color='#ff7f0e')

    ax1.axvline(pd.to_datetime(split_date), color='red', linestyle='--', alpha=0.6, label='Split Date')
    ax1.set_title(f'Strategy: {strategy_name}', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Equity')
    ax1.legend(loc='upper left')

    full_hist = pd.concat([hist_is, hist_os]).drop_duplicates(subset=['datetime']).sort_values('datetime')
    if not full_hist.empty:
        full_hist.set_index('datetime', inplace=True)
        full_hist['returns'] = full_hist['equity'].pct_change()
        
        window = 24 * 30 
        roll_mean = full_hist['returns'].rolling(window).mean()
        roll_std = full_hist['returns'].rolling(window).std()
        
        with np.errstate(divide='ignore', invalid='ignore'):
            roll_sharpe = (roll_mean / roll_std) * np.sqrt(24*365)
        
        ax2.plot(roll_sharpe.index, roll_sharpe, color='purple', linewidth=1, label='Rolling Sharpe (30D)')
        ax2.axhline(0, color='black', linewidth=0.5, linestyle='--')
        ax2.axvline(pd.to_datetime(split_date), color='red', linestyle='--', alpha=0.3)
        ax2.set_ylabel('Sharpe')
        ax2.legend(loc='upper left')

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
# 5. 主流程與策略載入 (全新 Class 架構)
# ==========================================
def load_strategy_from_file(filepath):
    """
    動態載入策略檔案，僅支援繼承 BaseAlpha 的 Strategy 類別。
    """
    import os, importlib.util
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"找不到檔案: {filepath}")
        
    module_name = os.path.basename(filepath).replace(".py", "")
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # 僅接受 Strategy 類別
    if hasattr(module, 'Strategy'):
        StrategyClass = getattr(module, 'Strategy')
        reqs = getattr(StrategyClass, 'requirements', [])
        return StrategyClass, reqs, module_name
    else:
        raise ValueError(f"[Error] 策略檔案 '{filepath}' 必須包含 'class Strategy(BaseAlpha):'")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('strategy_file', type=str)
    args = parser.parse_args()

    # 1. 載入策略類別與特徵需求
    try:
        StrategyClass, requirements, strategy_name = load_strategy_from_file(args.strategy_file)
        print(f"[BRAIN] 成功載入策略類別: {strategy_name}")
    except Exception as e:
        print(f"[Error] {e}")
        return

    # 2. 準備原始數據
    try:
        factory = BacktestDataFactory()
        df = factory.prepare_features("BTCUSDT", "1h", feature_ids=requirements)
        print(f"[BRAIN] 原始特徵載入完成，共 {len(df)} 筆。")
    except Exception as e:
        print(f"[Error] 數據準備失敗: {e}")
        return

    # 3. 實例化策略並進行動態加工
    print("[BRAIN] 實例化策略並進行動態特徵加工 (On-the-fly Calculation)...")
    strategy_instance = StrategyClass() # 使用預設參數
    df = strategy_instance.prepare_features(df)

    # 自動設定切分點 (若最後日期小於目標切分日，則取前 70%)
    target_split = pd.to_datetime("2025-06-01")
    if df['datetime'].max() < target_split:
        split_idx = int(len(df) * 0.7)
        SPLIT_DATE = df['datetime'].iloc[split_idx]
        print(f"[BRAIN] 歷史數據不足以使用目標日期，自動調整切分點為: {SPLIT_DATE}")
    else:
        SPLIT_DATE = target_split

    # 4. 執行全域回測
    print("--- 執行全域回測 ---")
    engine = PureBacktestEngine(df, initial_balance=10000, mode='next_open')
    
    # 將實例化後的 run 方法交給引擎執行
    engine.run(strategy_instance.run)
    
    # 取得回測歷史
    full_hist = pd.DataFrame(engine.account.equity_curve)
    
    if full_hist.empty:
        print("[Error] 回測結果為空 (可能完全沒有交易產生)")
        return

    # 切割 IS/OS 以供報告分析
    hist_is = full_hist[full_hist['datetime'] < SPLIT_DATE].copy()
    hist_os = full_hist[full_hist['datetime'] >= SPLIT_DATE].copy()

    # 5. 生成報告與繪圖
    print("[BRAIN] 產生最終報告與視覺化圖表...")
    save_report_to_file(df, hist_is, hist_os, SPLIT_DATE, strategy_name)
    plot_performance_advanced(df, hist_is, hist_os, SPLIT_DATE, strategy_name)
    print("[BRAIN] 回測流程全部完成！")

    # [可選功能] 如果你之前有加入 custom_logs，可以在此匯出 CSV 供除錯
    if hasattr(engine.account, 'custom_logs') and len(engine.account.custom_logs) > 0:
        debug_df = pd.DataFrame(engine.account.custom_logs)
        debug_csv_name = f"debug_data_{strategy_name}.csv"
        debug_df.to_csv(debug_csv_name, index=False, encoding='utf-8-sig')
        print(f"[BRAIN]  已匯出詳細變數日誌: {debug_csv_name}")


if __name__ == "__main__":
    main()