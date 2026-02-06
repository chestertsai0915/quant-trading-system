from .base_strategy import BaseStrategy
import indicators as ind
import numpy as np

class PriceVolume10(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy10_Volume_Diff_Reversion")
        
        # --- 策略參數 ---
        self.mean_window = 15     # 成交量均線週期
        
        self.upper_window = 60    # 上界分位數統計週期
        self.upper_q = 0.8        # 上界分位數 (0.8)
        
        self.lower_window = 100   # 下界分位數統計週期
        self.lower_q = 0.2        # 下界分位數 (0.2)

    def generate_signal(self):
        # 1. 數據長度檢查
        # 需求: SMA(15) + Diff(1) + Quantile(100) = 116
        # 安全邊際設 150
        if len(self.kline_data) < 150:
            return None

        # 2. 時間因子計算 (判斷是否為美股時間)
        df_with_time = ind.AlphaLibrary.add_us_market_open_flag(self.kline_data)
        is_trade_time = df_with_time['is_trade_time'].iloc[-1] # 1=美股開盤, 0=非美股

        # 3. 準備數據
        # 你的邏輯: feature1 = np.round(data['volume'], 0)
        # 其實 volume 本身就是數值，round 只是取整，對趨勢沒影響，直接用 vol 即可
        volume = df_with_time['vol'].values
        
        # ==========================================
        #  因子計算
        # ==========================================

        # A. 計算 feature1_mean (成交量 15 MA)
        # data['feature1_mean'] = rolling(15).mean()
        feature1_mean = ind.AlphaLibrary.calc_sma(volume, self.mean_window)

        # B. 計算 feature1_diff (均線的變化量)
        # data['feature1_diff'] = data['feature1_mean'].diff()
        feature1_diff = ind.AlphaLibrary.calc_difference(feature1_mean)

        # C. 計算滾動分位數閾值
        # upper = diff.rolling(60).quantile(0.8)
        upper_th = ind.AlphaLibrary.calc_rolling_quantile(feature1_diff, self.upper_window, self.upper_q)
        
        # lower = diff.rolling(100).quantile(0.2)
        lower_th = ind.AlphaLibrary.calc_rolling_quantile(feature1_diff, self.lower_window, self.lower_q)

        # ==========================================
        #  獲取當前數值
        # ==========================================
        
        curr_diff = feature1_diff[-1]
        curr_upper = upper_th[-1]
        curr_lower = lower_th[-1]

        # Debug Log
        # print(f"[{self.name}] Diff:{curr_diff:.2f} | Low:{curr_lower:.2f} | Up:{curr_upper:.2f} | US_Time:{is_trade_time}")

        # ==========================================
        #  進出場邏輯
        # ==========================================

        # 條件: is_trade_time == False (非美股時間)
        not_us_time = (is_trade_time == 0)

        # 進場: (Diff < Lower) & (非美股時間)
        long_condition = (curr_diff < curr_lower) and not_us_time
        
        # 出場: (Diff > Upper) & (非美股時間)
        exit_condition = (curr_diff > curr_upper) and not_us_time

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'Vol_Trend_Dip & Non_US_Time'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Vol_Trend_Spike & Non_US_Time'
            }
            
        return None