import inspect
import sys
import os
import pandas as pd

# 引用專案路徑
sys.path.append(os.getcwd())

try:
    from features import feature_definitions
    from features.feature_definitions import BaseFeature
except ImportError:
    print("[Error] 找不到 features 模組，請確認您在專案根目錄下執行。")
    sys.exit(1)

def get_default_args(func):
    """ 取得函式的參數與預設值 """
    signature = inspect.signature(func)
    return {
        k: v.default
        for k, v in signature.parameters.items()
        if v.default is not inspect.Parameter.empty and k != 'self'
    }

def main():
    print("\n" + "="*60)
    print(f"{'QUANT BRAIN 特徵庫 (Feature Library)':^60}")
    print("="*60)
    print(f"{'Feature Class':<25} | {'Prefix (ID開頭)':<15} | {'Parameters (參數)':<30}")
    print("-" * 75)

    count = 0
    # 掃描 feature_definitions 裡的所有類別
    for name, cls in inspect.getmembers(feature_definitions):
        if inspect.isclass(cls) and issubclass(cls, BaseFeature) and cls is not BaseFeature:
            
            # 1. 取得 Prefix
            prefix = getattr(cls, 'feature_prefix', 'N/A')
            
            # 2. 取得 __init__ 參數
            init_sig = inspect.signature(cls.__init__)
            params = []
            example_parts = []
            
            for param_name, param in init_sig.parameters.items():
                if param_name == 'self':
                    continue
                
                default_val = param.default
                if default_val is inspect.Parameter.empty:
                    params.append(f"{param_name}")
                    example_parts.append("X") # 必填
                else:
                    params.append(f"{param_name}={default_val}")
                    example_parts.append(str(default_val))
            
            params_str = ", ".join(params)
            
            # 3. 組合範例 ID
            # 規則通常是: prefix_param1_param2_v1
            # 但有些特徵可能有特殊的 id 生成邏輯，這裡做通用的模擬
            example_id = f"{prefix}_{'_'.join(example_parts)}_v1"
            
            print(f"{name:<25} | {prefix:<15} | {params_str}")
            # print(f"   Example ID: {example_id}") # 若想看範例 ID 可取消註解
            count += 1

    print("-" * 75)
    print(f"總計發現 {count} 個可用特徵模組。")
    print("="*60 + "\n")
    
    print("使用說明:")
    print("1. 在策略的 requirements 中，請使用 'Prefix' 加上參數來組合 ID。")
    print("2. 格式通常為: {Prefix}_{參數1}_{參數2}_v1")
    print("3. 例如 SMA_V1 的參數是 window=20, column='close' -> ID: sma_20_close_v1")
    print("\n")

if __name__ == "__main__":
    main()