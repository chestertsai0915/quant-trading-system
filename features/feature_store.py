import pandas as pd
import logging
import inspect
from .feature_engineer import FeatureEngineer
from . import feature_definitions 
from .feature_definitions import BaseFeature
import concurrent.futures
import pandas as pd
import logging
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

    def _compute_single_task(self, fid, data_board):
        """ 輔助函數：在執行緒中執行 get_or_create 和 compute """
        feature_obj = self._get_or_create_feature(fid)
        
        if not feature_obj:
            # 對應原本的 logging.warning，這裡先回傳狀態
            return fid, None, "NOT_FOUND"
            
        try:
            # 對應原本的 compute
            feat_df = feature_obj.compute(data_board)
            feat_df = feat_df.ffill()
            return fid, feat_df, None
        except Exception as e:
            # 對應原本的 logging.error
            return fid, None, e

    def load_features(self, feature_ids: list, data_board) -> pd.DataFrame:
        if data_board is None or data_board.main_kline.empty:
            return pd.DataFrame()

        base_df = data_board.main_kline[['open_time', 'close']].copy()
        
        # 使用 ThreadPoolExecutor 進行多執行緒計算
        # max_workers 預設為 CPU 核心數 * 5，適合 I/O 或釋放 GIL 的運算
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # 1. 提交所有任務 (並行開始)
            future_to_fid = {
                executor.submit(self._compute_single_task, fid, data_board): fid 
                for fid in feature_ids
            }
            
            # 2. 依序處理完成的結果 (串行合併)
            for future in concurrent.futures.as_completed(future_to_fid):
                fid = future_to_fid[future]
                
                try:
                    # 獲取執行緒回傳的結果
                    # returned_fid 為了確認沒搞混，feat_df 是計算結果，error 是異常
                    _, feat_df, error = future.result()

                    # --- 以下是你原本的邏輯判斷 ---

                    if error == "NOT_FOUND":
                        logging.warning(f"[FeatureStore] 無法解析特徵 ID: {fid} (請檢查拼寫或定義)")
                        base_df[fid] = 0
                        continue
                    
                    if isinstance(error, Exception):
                        logging.error(f"特徵計算失敗 {fid}: {error}")
                        base_df[fid] = 0
                        continue

                    # 成功計算，進行合併
                    if feat_df is None or feat_df.empty:
                        base_df[fid] = 0
                    else:
                        # [關鍵] 合併動作必須在主執行緒做，保證安全
                        base_df = self.engineer.attach_low_freq_feature(
                            base_df, feat_df, feature_cols=[fid], time_col='open_time'
                        )

                except Exception as e:
                    # 保護主迴圈不崩潰
                    logging.error(f"處理特徵結果時發生未預期錯誤 {fid}: {e}")
                    base_df[fid] = 0
        
        return base_df