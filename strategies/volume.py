from .base_strategy import BaseStrategy
import pandas as pd

class PriceVolume10(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy10_Volume_Diff_Reversion")
        
        # --- 策略參數 ---
        self.mean_window = 15     # 成交量均線週期
        
        self.upper_window = 60    # 上界分位數統計週期
        self.upper_q = 0.8        # 上界分位數
        
        self.lower_window = 100   # 下界分位數統計週期
        self.lower_q = 0.2        # 下界分位數

    def generate_signal(self):
        # ==========================================
        # 1. 定義需要的特徵 ID
        # ==========================================
        
        # A. 基礎數值: Volume SMA Diff
        # ID: vol_sma_diff_{sma}_v1
        fid_diff = f"vol_sma_diff_{self.mean_window}_v1"
        
        # B. 動態閾值 (Rolling Quantile)
        # 上界 (0.8)
        # ID: vol_sma_diff_quantile_{sma}_{roll}_{q}_v1
        fid_upper = f"vol_sma_diff_quantile_{self.mean_window}_{self.upper_window}_{self.upper_q}_v1"
        
        # 下界 (0.2)
        fid_lower = f"vol_sma_diff_quantile_{self.mean_window}_{self.lower_window}_{self.lower_q}_v1"
        
        # C. 時間濾網
        # ID: is_us_trade_time_v1 (無參數)
        fid_time = "is_us_trade_time_v1"

        # ==========================================
        # 2. 向 Feature Store 請求數據
        # ==========================================
        df = self.load_features([fid_diff, fid_upper, fid_lower, fid_time])
        
        # 安全檢查
        # 需求長度: SMA(15) + Rolling(100) = 115
        max_lookback = max(self.upper_window, self.lower_window) + self.mean_window
        if df.empty or len(df) < max_lookback + 20:
            return None

        required_cols = [fid_diff, fid_upper, fid_lower, fid_time]
        if not all(col in df.columns for col in required_cols):
            return None

        # ==========================================
        # 3. 交易邏輯
        # ==========================================
        
        curr = df.iloc[-1]
        
        # 取值
        curr_diff   = curr[fid_diff]
        curr_upper  = curr[fid_upper]
        curr_lower  = curr[fid_lower]
        is_us_time  = bool(curr[fid_time]) # 1=美股, 0=非美股

        # 條件: 非美股時間 (Not US Time)
        not_us_time = not is_us_time

        # 進場: (Diff < Lower) & (非美股時間)
        # 意義：成交量變化率過低 (量縮極致)，預期反轉或補量
        long_condition = (curr_diff < curr_lower) and not_us_time
        
        # 出場: (Diff > Upper) & (非美股時間)
        # 意義：成交量變化率過高 (爆量)，短線可能過熱
        exit_condition = (curr_diff > curr_upper) and not_us_time

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'Vol_Trend_Dip({curr_diff:.2f}<{curr_lower:.2f}) & Non_US_Time'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Vol_Trend_Spike & Non_US_Time'
            }
            
        return None