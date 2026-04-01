import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

def plot_equity_vs_benchmark(db_path=r"D:\investment\trading_data.db"):
    print(f" 正在讀取資料庫 {db_path} 中的快照數據...")
    
    # 1. 連接資料庫並讀取數據
    try:
        conn = sqlite3.connect(db_path)
        # 讀取時間、餘額、未實現損益、標的物價格
        query = """
            SELECT timestamp, total_balance, unrealized_pnl, btc_price 
            FROM snapshots 
            ORDER BY timestamp ASC
        """
        df = pd.read_sql(query, conn)
        conn.close()
    except Exception as e:
        print(f" 讀取資料庫失敗: {e}")
        return

    if df.empty:
        print(" 資料庫中沒有快照數據 (Snapshots)，可能機器人還沒紀錄到快照。")
        return
        
    # 2. 數據預處理
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    
    # 計算真實總權益 = 現金餘額 + 未實現損益
    df['total_equity'] = df['total_balance'] + df['unrealized_pnl']
    
    # 3. 計算歸一化報酬率 (基期設為 1.0，方便放在同一個刻度比較)
    initial_equity = df['total_equity'].iloc[0]
    initial_price = df['btc_price'].iloc[0]
    
    df['equity_return'] = df['total_equity'] / initial_equity
    df['benchmark_return'] = df['btc_price'] / initial_price

    # 4.  計算相關性 (Correlation)
    # 必須使用「每期報酬率(變化率)」來計算相關性，而非絕對數值
    df['equity_pct_change'] = df['total_equity'].pct_change()
    df['bench_pct_change'] = df['btc_price'].pct_change()
    
    # 計算 Pearson 相關係數 (忽略 NaN)
    correlation = df['equity_pct_change'].corr(df['bench_pct_change'])

    # 5. 計算其他績效指標
    total_ret = df['equity_return'].iloc[-1] - 1
    bench_ret = df['benchmark_return'].iloc[-1] - 1
    
    # 計算最大回撤 (Max Drawdown)
    df['equity_peak'] = df['equity_return'].cummax()
    df['drawdown'] = (df['equity_return'] - df['equity_peak']) / df['equity_peak']
    max_dd = df['drawdown'].min()

    df['bench_peak'] = df['benchmark_return'].cummax()
    df['bench_drawdown'] = (df['benchmark_return'] - df['bench_peak']) / df['bench_peak']
    bench_max_dd = df['bench_drawdown'].min()

    print(f" 數據處理完成！共 {len(df)} 筆快照。")
    print(f" 策略總報酬: {total_ret:.2%} | 最大回撤: {max_dd:.2%}")
    print(f" 標的總報酬: {bench_ret:.2%} | 最大回撤: {bench_max_dd:.2%}")
    print(f" 策略與標的相關性 (Correlation): {correlation:.4f}")

    # 6. 繪製圖表
    plt.figure(figsize=(14, 7))
    
    # 畫權益曲線與基準曲線
    plt.plot(df.index, df['equity_return'], label=f'Portfolio Equity (Ret: {total_ret:.2%}, MDD: {max_dd:.2%})', color='#1f77b4', linewidth=2)
    plt.plot(df.index, df['benchmark_return'], label=f'Benchmark Asset (Ret: {bench_ret:.2%}, MDD: {bench_max_dd:.2%})', color='#ff7f0e', alpha=0.7, linestyle='--')
    
    # 圖表美化設定 (將相關性加入標題)
    plt.title(f'Multi-Strategy Portfolio vs Benchmark)', fontsize=16, fontweight='bold')
    plt.xlabel('Date / Time', fontsize=12)
    plt.ylabel('Cumulative Return (1.0 = Initial Investment)', fontsize=12)
    
    # 時間軸格式化
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.gcf().autofmt_xdate() # 自動旋轉 X 軸日期標籤
    
    plt.legend(loc='upper left', fontsize=11, framealpha=0.9)
    plt.grid(True, linestyle='--', alpha=0.5)
    
    # 填充回撤區域 (視覺化虧損期)
    plt.fill_between(df.index, df['equity_return'], df['equity_peak'], color='red', alpha=0.1, label='Drawdown')
    
    # 儲存與顯示
    output_filename = 'portfolio_performance.png'
    plt.tight_layout()
    plt.savefig(output_filename, dpi=300)
    print(f" 圖表已成功儲存為 {output_filename}")
    
    try:
        plt.show()
    except:
        pass

if __name__ == "__main__":
    plot_equity_vs_benchmark()