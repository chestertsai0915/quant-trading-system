import pandas as pd
import numpy as np
import sys
import os

# 引用 System 模組
sys.path.append(os.getcwd())
try:
    from backtesting.pure_engine import PureBacktestEngine
    from backtesting.pure_engine import VirtualAccount # 用於 Type Hint
except ImportError:
    print("找不到 pure_engine，請確認路徑")

# ==========================================
# 1. 定義統一的策略邏輯 (Logic Injection)
# ==========================================
def apply_signals(df):
    """
    對傳入的 DF 計算訊號，確保邏輯一致
    """
    df = df.copy()
    
    # 1. 欄位映射 (Mapping)
    # 請根據你的 DF 實際欄位名稱修改這裡
    col_mad = 'mad_close_10_v1' if 'mad_close_10_v1' in df.columns else 'mad'
    col_bs = 'bs_ratio_v1' if 'bs_ratio_v1' in df.columns else 'bs_ratio'
    col_trade = 'is_us_trade_time_v1' if 'is_us_trade_time_v1' in df.columns else 'is_trade_time'
    
    # 2. 參數
    window = 25
    th1 = 0.8
    th2 = 0.9

    # 3. 計算特徵 (如果 DF 裡沒有算好的閾值)
    # 為了公平，我們現場算
    df['mad_th'] = df[col_mad].rolling(window).quantile(th1)
    df['bs_th'] = df[col_bs].rolling(window).quantile(th2)
    
    # 4. 產生訊號 (邏輯修正版：注意括號)
    # 條件 A: 進場
    cond_long = (df[col_mad] > df['mad_th']) & (df[col_bs] > df['bs_th'])
    
    # 條件 B: 出場 (括號非常重要!)
    cond_exit = (df[col_mad] < df['mad_th']) | (df[col_bs] < df['bs_th'])
    
    # 加上交易時間濾網
    is_trade = df[col_trade] if col_trade in df.columns else True
    
    df['long_signal'] = cond_long & (is_trade == 1)
    df['exit_signal'] = cond_exit & (is_trade == 1)
    
    return df

# ==========================================
# 2. Pandas PnL 算法 (Close-to-Close)
# ==========================================
def run_pandas_pnl(df_raw, initial_capital=10000):
    print("正在計算 Pandas PnL (收盤價成交)...")
    df = apply_signals(df_raw)
    
    # 模擬 Shift(1): 訊號 T 產生 -> T+1 持有
    df['long_shifted'] = df['long_signal'].shift(1).fillna(False)
    df['exit_shifted'] = df['exit_signal'].shift(1).fillna(False)
    
    # 計算 Position (State Machine Loop)
    position = 0
    pos_list = []
    for i in range(len(df)):
        if df['long_shifted'].iloc[i] and position == 0:
            position = 1
        elif df['exit_shifted'].iloc[i] and position == 1:
            position = 0
        pos_list.append(position)
    
    df['pos'] = pos_list
    
    # 計算 PnL: 持倉 * (今天的收盤 - 昨天的收盤) / 昨天的收盤
    # 這就是 "Close-to-Close"
    df['pct_chg'] = df['close'].pct_change().fillna(0)
    df['pnl'] = df['pos'].shift(1).fillna(0) * df['pct_chg']
    
    # 計算淨值
    df['equity'] = (1 + df['pnl']).cumprod() * initial_capital
    return df[['datetime', 'open', 'close', 'pos', 'equity']]

# ==========================================
# 3. System PnL 算法 (Next Open)
# ==========================================
def run_system_pnl(df_raw, initial_capital=10000):
    print("正在計算 System PnL (次一根開盤成交)...")
    # 這裡我們需要把 apply_signals 算好的閾值傳進去，避免重複計算誤差
    df_prepared = apply_signals(df_raw)
    
    # 定義 Adapter 策略：負責把 DF 的訊號轉給 Engine
    def adapter_strategy(row, account):
        # 直接讀取 apply_signals 算好的結果
        if row['long_signal']:
            if account.position == 0: return 'LONG', 1.0
        elif row['exit_signal']:
            if account.position > 0: return 'LONG_EXIT', 1.0
        return 'HOLD', 0

    # 啟動引擎 (Next Open 模式)
    engine = PureBacktestEngine(df_prepared, initial_balance=initial_capital, mode='next_open')
    engine.run(adapter_strategy)
    
    df_res = pd.DataFrame(engine.account.equity_curve)
    
    # 整理格式
    # System 的 equity_curve 可能只記錄有變動的時刻，需要與原時間軸對齊
    df_res['datetime'] = pd.to_datetime(df_res['datetime'])
    return df_res[['datetime', 'equity', 'position']]

# ==========================================
# 4. 主程式：比對與找兇手
# ==========================================
def compare_dataframes(df_pandas_raw, df_system_raw):
    # 1. 執行兩種算法
    res_pan = run_pandas_pnl(df_pandas_raw)
    res_sys = run_system_pnl(df_system_raw) # 雖然傳入 raw，但內部會重算訊號
    
    # 2. 合併對帳
    # 確保 datetime 格式一致
    res_pan['datetime'] = pd.to_datetime(res_pan['datetime'])
    res_sys['datetime'] = pd.to_datetime(res_sys['datetime'])
    
    merged = pd.merge(
        res_pan, 
        res_sys, 
        on='datetime', 
        how='left', 
        suffixes=('_pan', '_sys')
    )
    
    # 填補 System 空值 (沒交易時權益不變)
    merged['equity_sys'] = merged['equity_sys'].ffill().fillna(10000)
    merged['pos_sys'] = merged['position'].fillna(0)
    
    # 3. 計算差異
    merged['Diff_Equity'] = merged['equity_sys'] - merged['equity_pan']
    merged['Diff_Pos'] = merged['pos'] - merged['pos_sys']
    
    # 計算隔夜跳空 (Open - Prev Close)
    merged['Gap'] = merged['open'] - merged['close'].shift(1)
    merged['Gap_Pct'] = merged['Gap'] / merged['close'].shift(1)

    # 4. 輸出報告
    print("\n" + "="*60)
    print("【終極對帳報告】")
    print("="*60)
    
    final_pan = merged['equity_pan'].iloc[-1]
    final_sys = merged['equity_sys'].iloc[-1]
    
    print(f"Pandas 最終權益: {final_pan:.2f}")
    print(f"System 最終權益: {final_sys:.2f}")
    print(f"總金額差異: {final_sys - final_pan:.2f}")
    
    # 檢查持倉是否一致 (如果邏輯正確，這應該要是 0)
    diff_pos_count = (merged['Diff_Pos'] != 0).sum()
    print(f"持倉不一致筆數: {diff_pos_count}")
    if diff_pos_count == 0:
        print("✅ 持倉邏輯完美對齊！差異純粹來自成交價。")
    else:
        print("❌ 持倉邏輯仍有差異，請檢查數據源是否對齊。")

    # 找出「單日差異變化」最大的一天
    # 這代表那天發生了劇烈的「開盤跳空」，導致 Pandas 賺很大(或賠很大)但 System 沒跟到
    merged['Daily_Diff_Delta'] = merged['Diff_Equity'].diff()
    max_gap_idx = merged['Daily_Diff_Delta'].abs().idxmax()
    
    if pd.notna(max_gap_idx):
        row = merged.loc[max_gap_idx]
        print("\n[兇手抓到了] 造成差異最大的一筆交易:")
        print(f"日期: {row['datetime']}")
        print(f"當日 K 線: Open={row['open']}, Close={row['close']}")
        print(f"昨收 (Prev Close): {merged.loc[max_gap_idx-1, 'close']}")
        print(f"跳空幅度 (Gap): {row['Gap_Pct']:.4%}")
        print(f"Pandas 權益變化: {merged.loc[max_gap_idx, 'equity_pan'] - merged.loc[max_gap_idx-1, 'equity_pan']:.2f}")
        print(f"System 權益變化: {merged.loc[max_gap_idx, 'equity_sys'] - merged.loc[max_gap_idx-1, 'equity_sys']:.2f}")
        print("-" * 30)
        print("解析:")
        if row['Gap'] > 0:
            print("當天「跳空開高」。Pandas 假設買在昨收，賺到了跳空。System 買在今開，沒賺到。")
        else:
            print("當天「跳空開低」。Pandas 假設買在昨收，吃到了跳空跌幅。System 買在今開，避開了下跌。")

    return merged

# ==========================================
# 使用範例
# ==========================================
if __name__ == "__main__":
    # 假設你已經讀取了兩個 DF
    df_pandas = pd.read_csv(r'D:\investment\量化策略實裝\backtesting_data.csv')
    df_system = pd.read_csv(r'D:\investment\基於bitcoin量化多策略實作與多策略組合實作分析\testtttttttttttttt.csv')
    
    # 為了演示，我們讀取同一個檔案 (因為你想比對算法差異)
    try:
        
        # 這裡傳入兩個一樣的 DF，純粹比對「算法」
        # 如果你有兩個不同的 DF，請分別傳入
        compare_dataframes(df_pandas, df_system )
        
    except FileNotFoundError:
        print("找不到數據檔")