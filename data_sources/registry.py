# 1. 引入所有的 Fetcher
from .fear_greed import FearGreedFetcher
from .google_trends import GoogleTrendsFetcher
from .macro_economic import FredFetcher
from .us_stock import USStockFetcher

# 2. 建立註冊表清單
# 這裡列出所有你想啟用的 Fetcher Class (注意：是 Class 本身，不是實例)
_FETCHER_CLASSES = [
    FearGreedFetcher,
    GoogleTrendsFetcher,
    FredFetcher,
    USStockFetcher,
]

# 3. 自動生成字典 { "fear_greed": FearGreedFetcherClass, ... }
FETCHER_REGISTRY = {
    cls.name: cls 
    for cls in _FETCHER_CLASSES
}

def get_all_fetchers():
    """
    一次把所有 Fetcher 實例化並回傳
    這樣 main.py 只要呼叫這個函數，就能拿到所有工具
    """
    instances = {}
    for name, cls in FETCHER_REGISTRY.items():
        try:
            # 這裡假設所有 Fetcher 的 __init__ 都不需要參數
            # (參數都從 os.getenv 讀取)
            instances[name] = cls()
        except Exception as e:
            print(f" [Registry] 無法初始化 {name}: {e}")
    
    return instances