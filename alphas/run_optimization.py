import itertools
import time
import optuna
import warnings
import numpy as np
from research import ResearchEnvironment

optuna.logging.set_verbosity(optuna.logging.WARNING)
warnings.filterwarnings("ignore")

# ==========================================
# 核心轉換器：將統一格式轉為 Grid Search 所需的列表
# ==========================================
def parse_space_for_grid(search_space):
    param_grid = {}
    for key, config in search_space.items():
        if config["type"] == "categorical":
            param_grid[key] = config["choices"]
        elif config["type"] == "float":
            # 自動將 low, high, step 展開成 list，並四捨五入避免浮點數誤差
            low, high, step = config["low"], config["high"], config.get("step", 0.1)
            steps_count = int(round((high - low) / step)) + 1
            param_grid[key] = [round(low + i * step, 4) for i in range(steps_count)]
        elif config["type"] == "int":
            low, high, step = config["low"], config["high"], config.get("step", 1)
            param_grid[key] = list(range(low, high + 1, step))
    return param_grid

# ==========================================
# 優化引擎 1：Grid Search
# ==========================================
def run_grid_search(env, search_space):
    # 呼叫轉換器，自動產生 param_grid
    param_grid = parse_space_for_grid(search_space)
    
    keys, values = zip(*param_grid.items())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    
    print(f"--- 啟動 Grid Search (共 {len(combinations)} 組) ---")
    print(f"{'Params':<55} | {'Sharpe':<8} | {'Return':<8}")
    print("-" * 80)

    best_score = -999
    best_params = None

    for params in combinations:
        metrics = env.evaluate(params)
        
        score = metrics if isinstance(metrics, (int, float)) else metrics.get('sharpe', -999)
        ret = 0.0 if isinstance(metrics, (int, float)) else metrics.get('return', 0.0)

        print(f"{str(params):<55} | {score:>8.2f} | {ret:>8.2%}")

        if score > best_score:
            best_score = score
            best_params = params

    return best_params, best_score

# ==========================================
# 優化引擎 2：Optuna
# ==========================================
def run_optuna_search(env, search_space, n_trials=100, use_genetic=False):
    print(f"--- 啟動 Optuna 智慧優化 (預計執行 {n_trials} 次) ---")
    
    sampler = optuna.samplers.NSGAIISampler() if use_genetic else optuna.samplers.TPESampler()

    def objective(trial):
        # 自動根據 search_space 動態生成 Optuna 參數
        params = {}
        for key, config in search_space.items():
            if config["type"] == "categorical":
                params[key] = trial.suggest_categorical(key, config["choices"])
            elif config["type"] == "float":
                params[key] = trial.suggest_float(key, config["low"], config["high"], step=config.get("step"))
            elif config["type"] == "int":
                params[key] = trial.suggest_int(key, config["low"], config["high"], step=config.get("step", 1))

        # 評估參數
        metrics = env.evaluate(params)
        score = metrics if isinstance(metrics, (int, float)) else metrics.get('sharpe', -999)
        ret = 0.0 if isinstance(metrics, (int, float)) else metrics.get('return', 0.0)

        print(f"[Trial {trial.number:03d}] {str(params):<55} | Sharpe: {score:>6.2f} | Ret: {ret:>8.2%}")
        return score

    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(objective, n_trials=n_trials)

    return study.best_params, study.best_value

# ==========================================
# 主程式 (統一控制中心)
# ==========================================
def main():
    strategy_file = "alphas/alpha_tunable3.py"
    env = ResearchEnvironment(strategy_file, split_date="2025-06-01")

    # 唯一需要修改的地方：定義統一的搜索空間
    search_space = {
        "mad_ma_window": {"type": "categorical", "choices": [5, 10, 15, 25, 50, 75, 100]},
        "quanti_window": {"type": "categorical", "choices": [5, 10, 15, 25, 50, 75, 100, 150]},
        "weiht1": {"type": "float", "low": 0.2, "high": 0.8, "step": 0.1},
        
        # 如果未來有整數範圍，你可以這樣加：
        "factor_x": {
            "type": "categorical", 
            "choices": [ "bs_ratio_v1", "custom_atr_14_v1",  "smooth_obv_10_v1","vroc_20_v1", "custom_atr_7_v1","custom_atr_10_v1","custom_atr_14_v1","custom_atr_20_v1","custom_atr_30_v1","custom_atr_50_v1",]
        }
    }

    MODE = "optuna"  # "grid" 或 "optuna"
    
    start_time = time.time()

    if MODE == "grid":
        best_params, best_score = run_grid_search(env, search_space)
    elif MODE == "optuna":
        best_params, best_score = run_optuna_search(env, search_space, n_trials=200, use_genetic=True)

    elapsed = time.time() - start_time
    print("\n" + "="*60)
    print(f"最佳參數組合: {best_params}")
    print(f"最佳 Sharpe Ratio: {best_score:.4f}")
    print("="*60)

if __name__ == "__main__":
    main()