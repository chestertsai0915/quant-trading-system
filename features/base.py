from abc import ABC, abstractmethod
import pandas as pd

class BaseFeature(ABC):
    """
    所有特徵的基類 (Feature Interface)
    """
    name = "base_feature"
    version = "1.0"
    frequency = "1h" # 標記這個特徵的時間尺度 (1h, 1d, 5m...)
    description = ""

    @abstractmethod
    def compute(self, data_board) -> pd.Series:
        """
        輸入: DataBoard (包含所有原始數據)
        輸出: 計算好的特徵序列 (pd.Series)，索引必須是時間
        """
        pass

    def get_id(self):
        """ 特徵的唯一標識符 """
        return f"{self.name}_{self.version}"