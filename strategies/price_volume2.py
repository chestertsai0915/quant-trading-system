from .base_strategy import BaseStrategy
import pandas as pd

class PriceVolume2(BaseStrategy):
    def __init__(self):
        super().__init__(name="Price_Volume2")
        
        # --- 參數區 (對應 Feature ID) ---
        self.atr_win = 16        # ATR 窗口
        self.obv_win = 20        # OBV 窗口
        
        self.obv_ma_win = 5      # OBV 的 MA (訊號線)
        self.atr_ma_win = 30     # ATR 的 MA (訊號線)

    def generate_signal(self):
        # ==========================================
        # 1. 定義需要的特徵 ID
        # ==========================================
        
        # A. 基礎指標 (原本已有的定義)
        fid_atr = f"custom_atr_{self.atr_win}_v1"
        fid_obv = f"smooth_obv_{self.obv_win}_v1"
        
        # B. 訊號線 (剛剛新增的複合特徵)
        fid_atr_ma = f"custom_atr_ma_{self.atr_win}_{self.atr_ma_win}_v1"
        fid_obv_ma = f"smooth_obv_ma_{self.obv_win}_{self.obv_ma_win}_v1"

        # ==========================================
        # 2. 向 Feature Store 請求數據
        # ==========================================
        df = self.load_features([fid_atr, fid_obv, fid_atr_ma, fid_obv_ma])
        
        # 安全檢查 (MA 需要較長的數據)
        min_len = max(self.atr_ma_win, self.obv_ma_win) + 20
        if df.empty or len(df) < min_len:
            return None

        # 檢查欄位是否存在
        required_cols = [fid_atr, fid_obv, fid_atr_ma, fid_obv_ma]
        if not all(col in df.columns for col in required_cols):
            return None

        # ==========================================
        # 3. 交易邏輯
        # ==========================================
        
        curr = df.iloc[-1]
        
        # 數值提取
        curr_atr    = curr[fid_atr]
        curr_atr_ma = curr[fid_atr_ma]
        
        curr_obv    = curr[fid_obv]
        curr_obv_ma = curr[fid_obv_ma]

        # 決策邏輯 (Logic)
        
        # 進場: (OBV > OBV_MA) & (ATR > ATR_MA)
        long_condition = (curr_obv > curr_obv_ma) and (curr_atr > curr_atr_ma)
        
        # 出場: (OBV < OBV_MA) | (ATR < ATR_MA)
        exit_condition = (curr_obv < curr_obv_ma) or (curr_atr < curr_atr_ma)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'Entry: OBV({curr_obv:.1f})>MA & ATR>MA'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Exit: OBV({curr_obv:.1f})<MA or ATR<MA'
            }
            
        return None