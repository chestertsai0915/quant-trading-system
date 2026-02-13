import pandas as pd
import logging
import inspect
from .feature_engineer import FeatureEngineer
from . import feature_definitions 
from .feature_definitions import BaseFeature

class FeatureStore:
    def __init__(self):
        self.registry = {} 
        self.engineer = FeatureEngineer()
        # 初始化時先不預先註冊，全部改為 Lazy Loading (用到時才動態建立)
        # 這樣最省資源

    def _get_or_create_feature(self, fid):
        """ 根據 ID 獲取特徵實例，如果沒有就動態建立 """
        
        # 1. 快取命中
        if fid in self.registry:
            return self.registry[fid]

        # 2. 動態解析
        # 遍歷 feature_definitions 裡的所有類別
        for name, cls in inspect.getmembers(feature_definitions):
            if inspect.isclass(cls) and issubclass(cls, BaseFeature) and cls is not BaseFeature:
                # 問每個類別：這個 ID 是你的嗎？如果是，請給我實例
                instance = cls.from_id(fid)
                if instance:
                    self.registry[fid] = instance
                    # logging.info(f"[FeatureStore] 動態建立特徵: {fid} -> {name}")
                    return instance
        
        return None

    def load_features(self, feature_ids: list, data_board) -> pd.DataFrame:
        if data_board is None or data_board.main_kline.empty:
            return pd.DataFrame()

        base_df = data_board.main_kline[['open_time', 'close']].copy()
        
        for fid in feature_ids:
            feature_obj = self._get_or_create_feature(fid)
            
            if not feature_obj:
                logging.warning(f"[FeatureStore] 無法解析特徵 ID: {fid} (請檢查拼寫或定義)")
                base_df[fid] = 0
                continue
                
            try:
                feat_df = feature_obj.compute(data_board)
                
                if feat_df.empty:
                    base_df[fid] = 0
                else:
                    base_df = self.engineer.attach_low_freq_feature(
                        base_df, feat_df, feature_cols=[fid], time_col='open_time'
                    )
            except Exception as e:
                logging.error(f"特徵計算失敗 {fid}: {e}")
                base_df[fid] = 0
        
        return base_df