from .base_strategy import BaseStrategy
import indicators as ind
import numpy as np

class PriceVolume1(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy1_MAD_BSR")
        
        # --- 策略參數 (完全依照你提供的數值) ---
        self.window = 25
        self.th1 = 0.8  # MAD 的分位數閾值
        self.th2 = 0.9  # BS_Ratio 的分位數閾值
        
        # MAD 計算本身的 SMA 週期 (原本回測代碼中似乎有用到 talib.SMA(10) 來算 MAD)
        # 假設你的 mad 是用 10日均線計算偏離
        self.mad_ma_period = 10 

    def generate_signal(self):
        # 1. 數據長度檢查
        # 需要: MAD(10) -> Rolling(25) -> Quantile
        # 至少需要 10 + 25 = 35 根，保險起見設 50
        if len(self.kline_data) < 50:
            return None

        # 2. 時間因子計算
        # 這一步會回傳一個加上了 'is_trade_time' 欄位的 df
        df_with_time = ind.AlphaLibrary.add_us_market_open_flag(self.kline_data)
        
        # 3. 準備 Numpy Array
        close = df_with_time['close'].values
        high = df_with_time['high'].values
        low = df_with_time['low'].values
        
        # ==========================================
        #  因子計算
        # ==========================================

        # A. 計算 MAD (使用 close, 預設 MA=10)
        # data['mad'] = (close - ma) / ma
        mad = ind.AlphaLibrary.calc_mad(close, window=self.mad_ma_period)

        # B. 計算 BS Ratio
        # data['bs_ratio'] = (close - low) / (high - close)
        bs_ratio = ind.AlphaLibrary.calc_bs_ratio(high, low, close)

        # C. 計算滾動分位數閾值 (Rolling Quantile)
        # data['mad'].rolling(window).quantile(th1)
        mad_quantile = ind.AlphaLibrary.calc_rolling_quantile(mad, self.window, self.th1)
        
        # data['bs_ratio'].rolling(window).quantile(th2)
        bs_quantile = ind.AlphaLibrary.calc_rolling_quantile(bs_ratio, self.window, self.th2)

        # ==========================================
        #  獲取當前數值 (Current Step)
        # ==========================================
        
        # 對應 shift(1).fillna(False) 的邏輯：
        # 實盤中，當 K 線收盤 (Close) 時，我們拿到的是 illoc[-1]，這就是回測中 shift(1) 的那個時間點
        # 我們根據這個剛收盤的數據，來決定「下一個 Open」要不要動作
        
        curr_mad = mad[-1]
        curr_bs = bs_ratio[-1]
        
        curr_mad_th = mad_quantile[-1]
        curr_bs_th = bs_quantile[-1]
        
        is_trade_time = df_with_time['is_trade_time'].iloc[-1]

        # Debug Log (觀察數值用)
        # print(f"MAD:{curr_mad:.4f} (Th:{curr_mad_th:.4f}) | BS:{curr_bs:.2f} (Th:{curr_bs_th:.2f}) | Time:{is_trade_time}")

        # ==========================================
        #  進出場條件 (Logic)
        # ==========================================

        # data['long_signal'] = (mad > mad_th) & (bs > bs_th) & (time==True)
        long_condition = (curr_mad > curr_mad_th) and \
                         (curr_bs > curr_bs_th) and \
                         (is_trade_time)

        # data['exit_signal'] = (mad < mad_th) | (bs < bs_th) & (time==True)
        # 注意：這裡解釋為 (條件A 或 條件B) 且 在交易時間內
        exit_condition = ((curr_mad < curr_mad_th) or (curr_bs < curr_bs_th)) and \
                         (is_trade_time)

        # 回傳訊號
        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005, # 之後由資金管理模組決定
                'reason': f'MAD({curr_mad:.4f})>Th & BS({curr_bs:.2f})>Th'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'MAD or BS fell below Threshold'
            }
            
        return None