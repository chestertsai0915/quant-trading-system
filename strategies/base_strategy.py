import pandas as pd
import talib
from abc import ABC, abstractmethod




class BaseStrategy(ABC):
    def __init__(self, name):
        self.name = name
        self.kline_data = pd.DataFrame()
        self.external_data = {} # 預留給外部資料的容器

    def update_data(self, klines_df, external_data=None):
        """
        主程式會呼叫這個函數，把最新的數據餵進來
        """
        self.kline_data = klines_df
        if external_data:
            self.external_data.update(external_data)

    def warm_up(self, historical_kline):
        """
        機器人啟動時的熱機動作
        目的：讓 rolling(window) 等指標有足夠的歷史數據可以計算
        """
        print(f"[{self.name}] 正在熱機... (載入 {len(historical_kline)} 筆 K 線)")
        
        # 將歷史數據直接設為當前數據
        self.kline_data = historical_kline

    @abstractmethod
    def generate_signal(self):
        """
        每個子策略都必須實作這個函數
        回傳: 
        {
            'symbol': 'BTCUSDT',
            'action': 'LONG'/'SHORT'/'CLOSE',
            'quantity': 0.1,
            'reason': 'RSI < 30'
        }
        """
        pass
    
    # 這裡封裝常用的 talib，讓子策略寫起來更乾淨
    def get_close(self):
        return self.kline_data['close'].values