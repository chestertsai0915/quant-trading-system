from .base_strategy import BaseStrategy
import indicators as ind  # 引用根目錄的 indicators.py
import numpy as np

class PriceVolume2(BaseStrategy):
    def __init__(self):
        super().__init__(name="Price_Volume2")
        
        # --- 參數區 (方便未來調整) ---
        self.atr_window = 16         # 因子參數
        self.obv_window = 20         # 因子參數
        
        self.signal_obv_ma = 5       # 訊號參數 (window1)
        self.signal_atr_ma = 30      # 訊號參數 (window2)

    def generate_signal(self):
        # 1. 數據長度檢查 (因為要算多次 MA，建議留長一點 buffer)
        if len(self.kline_data) < 60:
            return None

        # 2. 準備 Raw Data (轉成 numpy array)
        close = self.kline_data['close'].values
        high = self.kline_data['high'].values
        low = self.kline_data['low'].values
        volume = self.kline_data['volume'].values

        # ==========================================
        #  呼叫共用因子庫 (核心改變)
        # ==========================================
        
        # 呼叫自定義 ATR
        my_atr = ind.AlphaLibrary.calc_custom_atr(high, low, close, self.atr_window)
        
        # 呼叫自定義 OBV
        my_obv = ind.AlphaLibrary.calc_smooth_obv(close, volume, self.obv_window)

        # ==========================================
        #  計算進出場訊號線
        # ==========================================
        
        # 計算訊號判斷用的 MA (OBV 的 5日均線, ATR 的 30日均線)
        obv_ma_line = ind.AlphaLibrary.calc_sma(my_obv, self.signal_obv_ma)
        atr_ma_line = ind.AlphaLibrary.calc_sma(my_atr, self.signal_atr_ma)

        # 取得「最新一根 (剛收盤)」的數值
        curr_obv = my_obv[-1]
        curr_obv_ma = obv_ma_line[-1]
        
        curr_atr = my_atr[-1]
        curr_atr_ma = atr_ma_line[-1]

        # Log (方便 Debug)
        # print(f"[{self.name}] OBV:{curr_obv:.2f} vs MA:{curr_obv_ma:.2f} | ATR:{curr_atr:.4f} vs MA:{curr_atr_ma:.4f}")

        # ==========================================
        #  決策邏輯 (Logic)
        # ==========================================

        # 進場條件: (OBV > OBV_MA) & (ATR > ATR_MA)
        long_condition = (curr_obv > curr_obv_ma) and (curr_atr > curr_atr_ma)
        
        # 出場條件: (OBV < OBV_MA) | (ATR < ATR_MA)
        exit_condition = (curr_obv < curr_obv_ma) or (curr_atr < curr_atr_ma)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,  # Phase 3 會改成動態計算
                'reason': f'Entry: OBV({curr_obv:.1f})>MA & ATR>MA'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Exit: OBV({curr_obv:.1f})<MA or ATR<MA'
            }
            
        return None