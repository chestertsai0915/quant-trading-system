from .base_strategy import BaseStrategy
import pandas as pd

class PriceVolume8(BaseStrategy):
    def __init__(self):
        super().__init__()
        
        # --- 參數映射 ---
        self.mad_period = 10   # MAD 計算週期
        self.window = 30       # 滾動視窗 (計算分位數用)
        self.th1 = 0.7         # MAD 閾值 (70% 中高波動)
        self.th2 = 0.9         # BS Ratio 閾值 (90% 極強買壓)

    def generate_signal(self):
        # ==========================================
        # 1. 定義需要的特徵 ID
        # ==========================================
        
        # A. 基礎指標數值
        # MAD_V1 -> mad_{col}_{win}_v1
        fid_mad = f"mad_close_{self.mad_period}_v1"
        
        # BSRatio_V1 -> bs_ratio_v1 (無參數)
        fid_bs = "bs_ratio_v1"
        
        # B. 動態閾值線 (Rolling Quantile)
        # MAD 閾值 (MAD_Quantile_V1)
        fid_mad_th = f"mad_quantile_{self.mad_period}_{self.window}_{self.th1}_v1"
        
        # BS Ratio 閾值 (BSRatio_Quantile_V1)
        # ID: bs_quantile_{roll}_{q}_v1
        fid_bs_th = f"bs_quantile_{self.window}_{self.th2}_v1"

        # ==========================================
        # 2. 向 Feature Store 請求數據
        # ==========================================
        df = self.load_features([fid_mad, fid_bs, fid_mad_th, fid_bs_th])
        
        # 安全檢查
        if df.empty or len(df) < self.window + 20:
            return None

        required_cols = [fid_mad, fid_bs, fid_mad_th, fid_bs_th]
        if not all(col in df.columns for col in required_cols):
            return None

        # ==========================================
        # 3. 交易邏輯
        # ==========================================
        
        curr = df.iloc[-1]
        
        # 取值
        curr_mad    = curr[fid_mad]
        curr_bs     = curr[fid_bs]
        curr_mad_th = curr[fid_mad_th]
        curr_bs_th  = curr[fid_bs_th]

        # 進場: 波動率放大 (MAD > 70%) 且 買壓極強 (BS > 90%)
        long_condition = (curr_mad > curr_mad_th) and (curr_bs > curr_bs_th)
        
        # 出場: 波動率冷卻 (MAD < 70%) 且 買壓退潮 (BS < 90%)
        # 注意：這裡維持 AND 邏輯，需兩者同時滿足才出場
        exit_condition = (curr_mad < curr_mad_th) and (curr_bs < curr_bs_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'HighVol({curr_mad:.4f}) & Extreme_Buy({curr_bs:.2f})'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Vol_Cool & Buy_Weak'
            }
            
        return None