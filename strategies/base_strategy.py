from abc import ABC, abstractmethod
import pandas as pd
from features.feature_engineer import FeatureEngineer

class BaseStrategy(ABC):
    def __init__(self, name):
        self.name = name
        # 策略預設只看主頻率數據，保留這變數讓舊策略不用改
        self.kline_data = pd.DataFrame() 
        self.data_board = None 
        # 每個策略都擁有特徵工程師能力
        self.feature_engineer = FeatureEngineer()

    def update_data(self, data_board):
        """
        接收 DataBoard
        """
        if data_board is None or data_board.main_kline.empty:
            return

        self.data_board = data_board
        # 預設將主頻率 K 線給策略使用 -> 相容舊策略邏輯
        self.kline_data = data_board.main_kline
        
    @abstractmethod
    def generate_signal(self):
        """
        子類別實作交易邏輯
        """
        pass
    
    # --- 新增：主動式特徵合成 (Superposition via Feature Engineering) ---
    def enrich_data_with_external(self, source_name, feature_cols, rename_map=None):
        """
        策略層決定何時、如何混合頻率。
        """
        if not self.data_board:
            return self.kline_data
            
        external_df = self.data_board.external_data.get(source_name)
        # 注意：這裡如果是 None，會傳進去 attach_low_freq_feature
        # 但我們已經在 FeatureEngineer 裡加了 None 檢查，所以這裡安全
        
        enriched_df = self.feature_engineer.attach_low_freq_feature(
            high_freq_df=self.kline_data,
            low_freq_df=external_df,
            feature_cols=feature_cols,
            rename_map=rename_map  # [Fix] 傳遞參數
        )
        
        return enriched_df

    # --- 狀態查詢 ---
    def get_external_state(self, source_name, col_name=None):
        if self.data_board:
            return self.data_board.get_latest_state(source_name, col_name)
        return None

    def get_close(self):
        return self.kline_data['close'].values