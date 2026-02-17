import itertools
import time
from research import ResearchEnvironment

def main():
    # 1. 設定目標
    strategy_file = "alphas/alpha_tunable.py"
    split_date = "2025-06-01" # 訓練資料截止日
    
    # 2. 初始化環境 (資料只會載入一次)
    env = ResearchEnvironment(strategy_file, split_date=split_date)

    # 3. 定義參數網格 (Grid Search Space)
    # 這裡定義你想測試的參數範圍
    param_grid = {
        "rsi_lower": [20, 25, 30, 35],
        "rsi_upper": [65, 70, 75, 80],
        "zscore_entry": [-1.0, -1.5, -2.0]
    }

    # 產生所有組合
    keys, values = zip(*param_grid.items())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    
    print(f"開始網格搜索 (Grid Search)... 共 {len(combinations)} 組參數")
    print(f"{'No.':<5} | {'Params':<45} | {'Sharpe':<8} | {'Return':<8}")
    print("-" * 80)

    best_score = -999
    best_params = None
    results = []

    start_time = time.time()

    # 4. 開始迴圈
    for i, params in enumerate(combinations):
        # 呼叫 research.evaluate
        metrics = env.evaluate(params)
        
        score = metrics['sharpe']
        ret = metrics['return']
        
        # 紀錄結果
        results.append({
            "params": params,
            "metrics": metrics
        })

        # 印出進度 (可以每 10 次印一次，這裡為了演示每次印)
        print(f"{i+1:<5} | {str(params):<45} | {score:>8.2f} | {ret:>8.2%}")

        # 更新最佳解
        if score > best_score:
            best_score = score
            best_params = params

    end_time = time.time()
    
    # 5. 報告結果
    print("\n" + "="*50)
    print("優化完成 (Optimization Completed)")
    print(f"耗時: {end_time - start_time:.2f} 秒")
    print("="*50)
    print(f"最佳參數: {best_params}")
    print(f"最佳 Sharpe: {best_score:.4f}")
    
    # 如果找到了最佳參數，提示使用者可以拿去 brain.py 驗證
    print("-" * 50)
    print("下一步：")
    print("1. 將最佳參數填入 alphas/alpha_tunable.py 的 default_params")
    print("2. 執行 'python run.py' (brain) 進行 OS 驗證")

if __name__ == "__main__":
    main()