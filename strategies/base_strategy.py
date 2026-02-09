import pandas as pd
import talib
from abc import ABC, abstractmethod




from abc import ABC, abstractmethod
import pandas as pd
import logging

class BaseStrategy(ABC):
    def __init__(self, name):
        self.name = name
        # 這裡只存最新的那一張大表
        self.kline_data = pd.DataFrame() 
        self.external_data = {} # 雖然 Stateless 主要用 kline_data，但保留這個讓你看最新值也很方便

    def update_data(self, df):
        """
        核心更新方法：
        接收來自 DataManager 的完整歷史資料 (含外部數據)
        """
        if df.empty:
            return

        self.kline_data = df
        
        # 順便更新一下 external_data (方便 log 或簡單存取)
        # 取最後一筆 (最新狀態)
        latest = df.iloc[-1]
        self.external_data = {col: latest[col] for col in df.columns}

    @abstractmethod
    def generate_signal(self):
        """
        子類別必須實作這個方法
        回傳: dict (action, quantity, reason) 或 None
        """
        pass
    
    # 這裡封裝常用的 talib，讓子策略寫起來更乾淨
    def get_close(self):
        return self.kline_data['close'].values