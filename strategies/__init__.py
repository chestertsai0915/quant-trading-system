import os
import pkgutil
import importlib
import inspect
from strategies.base_strategy import BaseStrategy 

# 這是我們的策略倉庫，自動填入
STRATEGY_MAP = {}

def _auto_register_strategies():
    """
    自動掃描當前資料夾下的所有 .py 檔案，
    找出繼承自 BaseStrategy 的類別，並放入 STRATEGY_MAP。
    """
    # 取得當前資料夾路徑
    package_dir = os.path.dirname(__file__)
    
    # 走訪資料夾內所有模組
    for _, module_name, _ in pkgutil.iter_modules([package_dir]):
        # 跳過 base_strategy 避免重複或循環引用
        if module_name == 'base_strategy':
            continue
            
        try:
            # 動態 import 模組 (例如: import strategies.test_loop)
            module = importlib.import_module(f".{module_name}", __package__)
            
            # 檢查模組內的所有屬性
            for attribute_name in dir(module):
                attribute = getattr(module, attribute_name)
                
                # 判斷條件：
                # 1. 必須是個類別 (class)
                # 2. 必須繼承自 BaseStrategy
                # 3. 不能是 BaseStrategy 本身
                if (inspect.isclass(attribute) and 
                    issubclass(attribute, BaseStrategy) and 
                    attribute is not BaseStrategy):
                    
                    # 註冊到字典中，Key 是類別名稱 (例如 "TestLoop")
                    STRATEGY_MAP[attribute.__name__] = attribute
                    print(f"[SYSTEM] 自動載入策略: {attribute.__name__}")
                    
        except Exception as e:
            print(f"[ERROR] 載入策略 {module_name} 失敗: {e}")

# 執行自動註冊
_auto_register_strategies()