from abc import ABC, abstractmethod
import pandas as pd
from features.feature_store import FeatureStore # 引入商店

class BaseStrategy(ABC):
    def __init__(self, name=None):
        # 如果沒傳名字，自動用 Class Name (例如 "PriceVolume2")
        if name is None:
            self.name = self.__class__.__name__ 
        else:
            self.name = name
               
        self.kline_data = pd.DataFrame() 
        self.data_board = None 
        
        # [NEW] 每個策略都配給一個特徵商店入口
        # (實務上 FeatureStore 可以是單例模式 Singleton，省記憶體)
        self.feature_store = FeatureStore()

    def update_data(self, data_board):
        self.data_board = data_board
        self.kline_data = data_board.main_kline
        
    @abstractmethod
    def generate_signal(self):
        pass
    # --- [NEW] 策略專用的特徵載入方法 ---
    def load_features(self, feature_list):
        """
        策略只需要給清單，剩下的髒活 (計算、對齊、合併) 全由底層處理。
        """
        if not self.data_board:
            return pd.DataFrame()
            
        return self.feature_store.load_features(feature_list, self.data_board)