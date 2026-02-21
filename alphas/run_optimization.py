import itertools
import time
from research import ResearchEnvironment

def main():
    strategy_file = "alphas/alpha_tunable3.py"
    
    # 1. 初始化環境
    # 寫死的 requirements
    env = ResearchEnvironment(strategy_file, split_date="2025-06-01")

    # 2. 定義參數網格 (這些名稱要跟策略裡的 params.get 對應)
    param_grid = {
        "rsi_buy_th": [20, 25, 30, 35],
        "z_buy_th":   [-1.0, -1.5, -2.0],
        "z_sell_th":  [0.0, 0.5]
    }

    # 產生組合
    keys, values = zip(*param_grid.items())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    
    print(f"開始優化共 {len(combinations)} 組參數")
    print(f"{'Params':<55} | {'Sharpe':<8} | {'Return':<8}")
    print("-" * 80)

    best_score = -999
    best_params = None

    for i, params in enumerate(combinations):
        # 執行 evaluate
        metrics = env.evaluate(params)
        
        # 防呆
        if isinstance(metrics, (int, float)):
            score = metrics
            ret = 0.0
        else:
            score = metrics['sharpe']
            ret = metrics['return']

        print(f"{str(params):<55} | {score:>8.2f} | {ret:>8.2%}")

        if score > best_score:
            best_score = score
            best_params = params

    print("\n" + "="*50)
    print(f"最佳參數: {best_params}")
    print(f"最佳 Sharpe: {best_score:.4f}")

if __name__ == "__main__":
    main()