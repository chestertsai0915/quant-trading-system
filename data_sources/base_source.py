from abc import ABC, abstractmethod
import pandas as pd

class BaseDataSource(ABC):
    # 每個子類別都必須定義這個名字
    name: str = "base"

    @abstractmethod
    def fetch_data(self, **kwargs) -> pd.DataFrame:
        """
        必須回傳 DataFrame，包含 standard columns:
        ['open_time', 'symbol', 'metric', 'value']
        """
        pass