import pandas as pd
import logging
import sys
import os

# 確保可以引用專案根目錄的模組
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from utils.database import DatabaseHandler
from features.feature_store import FeatureStore
from managers.data_manager import DataBoard 

class BacktestDataFactory:
    def __init__(self, db_path="trading_data.db"):
        self.db = DatabaseHandler(db_path, skip_backup=True)
        self.feature_store = FeatureStore()

    def _load_all_external_data(self, start_time=None):
        """ 載入外部數據 (保持不變) """
        print(" [Factory] 正在載入外部數據環境...")
        snapshot = {}
        default_limit = 50000 

        metrics_map = {
            'fear_greed': ['fear_greed'],
            'funding_rate': ['funding_rate'],
            'google_trends': ['google_trends_BTC'],
            'fred_macro': ['yield_10y', 'fed_assets']
        }

        # 1. QQQ
        qqq_df = self.db.load_market_data('QQQ', '1d', limit=2000)
        if not qqq_df.empty:
            snapshot['us_stock_qqq'] = qqq_df

        # 2. External
        for source, metrics in metrics_map.items():
            dfs = []
            for metric in metrics:
                target_symbol = "BTCUSDT" if source == 'funding_rate' else "GLOBAL"
                df = self.db.load_external_data(target_symbol, metric, start_time=start_time, limit=default_limit)
                if not df.empty:
                    df['metric'] = metric
                    dfs.append(df)
            
            if dfs:
                merged = pd.concat(dfs, ignore_index=True).sort_values('open_time')
                snapshot[source] = merged

        return snapshot

    def prepare_features(self, symbol, interval, feature_ids, start_time=None, end_time=None):
        """
        動態準備特徵數據
        :param feature_ids: 策略指定的特徵 ID 列表 (List[str])
        """
        print(f" [Factory] 正在為 {symbol} ({interval}) 準備數據...")
        
        # 1. 讀取主 K 線
        main_df = self.db.load_market_data(symbol, interval, limit=50000)
        if main_df.empty:
            raise ValueError(f"資料庫無 {symbol} K 線數據")

        main_df['datetime'] = pd.to_datetime(main_df['open_time'], unit='ms')
        main_df = main_df.sort_values('datetime').reset_index(drop=True)

        # 2. 準備 DataBoard
        start_ts = int(main_df['open_time'].min())
        external_data = self._load_all_external_data(start_time=start_ts)
        data_board = DataBoard(main_kline=main_df, external_data=external_data)

        # 3. [關鍵] 根據傳入的 ID 動態計算
        if feature_ids:
            print(f" [Factory] 策略要求 {len(feature_ids)} 個特徵，正在計算...")
            try:
                # FeatureStore 會自動解析 ID (如 sma_10, sma_20) 並分別實例化
                features_df = self.feature_store.load_features(feature_ids, data_board)
            except Exception as e:
                print(f" [Error] FeatureStore 計算失敗: {e}")
                features_df = pd.DataFrame()
        else:
            print(" [Factory] 策略無特徵需求，僅回傳原始 K 線")
            features_df = pd.DataFrame()

        # 4. 合併
        if features_df.empty:
            final_df = main_df
        else:
            if 'open_time' in features_df.columns:
                features_df['open_time'] = features_df['open_time'].astype('int64')
            
            # Left Join 確保 K 線完整
            final_df = pd.merge(main_df, features_df.drop(columns=['close'], errors='ignore'), on='open_time', how='left')

        # 5. 時間篩選 & 清洗
        if start_time:
            final_df = final_df[final_df['datetime'] >= pd.to_datetime(start_time)]
        if end_time:
            final_df = final_df[final_df['datetime'] <= pd.to_datetime(end_time)]

        final_df = final_df.ffill().fillna(0)
        
        print(f" [Factory] 數據準備完成! Shape: {final_df.shape}")
        return final_df