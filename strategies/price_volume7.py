from .base_strategy import BaseStrategy
import pandas as pd

class PriceVolume7(BaseStrategy):
    def __init__(self):
        super().__init__()
        
        # --- 參數映射 ---
        self.mom_period = 10   # Momentum 週期
        self.mom_smooth = 5    # Momentum 平滑週期
        self.mad_period = 10   # MAD 計算週期
        
        self.window = 25       # 滾動視窗 (計算分位數用)
        self.th1 = 0.7         # Momentum 閾值 (70% 強勢)
        self.th2 = 0.1         # MAD 閾值 (10% 低波過濾)

    def generate_signal(self):
        # ==========================================
        # 1. 定義需要的特徵 ID
        # ==========================================
        
        # A. 基礎指標數值
        # SmoothMomentum_V1 -> smooth_mom_{mom}_{smooth}_v1
        fid_mom = f"smooth_mom_{self.mom_period}_{self.mom_smooth}_v1"
        
        # MAD_V1 -> mad_{col}_{win}_v1 (假設 column 預設為 close)
        fid_mad = f"mad_close_{self.mad_period}_v1"
        
        # B. 動態閾值線 (Rolling Quantile)
        # Momentum 閾值 (SmoothMomentum_Quantile_V1)
        # ID: smooth_mom_quantile_{mom}_{smooth}_{roll}_{q}_v1
        fid_mom_th = f"smooth_mom_quantile_{self.mom_period}_{self.mom_smooth}_{self.window}_{self.th1}_v1"
        
        # MAD 閾值 (MAD_Quantile_V1)
        # ID: mad_quantile_{mad}_{roll}_{q}_v1
        fid_mad_th = f"mad_quantile_{self.mad_period}_{self.window}_{self.th2}_v1"

        # ==========================================
        # 2. 向 Feature Store 請求數據
        # ==========================================
        df = self.load_features([fid_mom, fid_mad, fid_mom_th, fid_mad_th])
        
        # 安全檢查
        if df.empty or len(df) < self.window + 20:
            return None

        required_cols = [fid_mom, fid_mad, fid_mom_th, fid_mad_th]
        if not all(col in df.columns for col in required_cols):
            return None

        # ==========================================
        # 3. 交易邏輯
        # ==========================================
        
        curr = df.iloc[-1]
        
        # 取值
        curr_mom    = curr[fid_mom]
        curr_mad    = curr[fid_mad]
        curr_mom_th = curr[fid_mom_th]
        curr_mad_th = curr[fid_mad_th]

        # 進場: 動能強 (Mom > 70%) 且 波動率正常 (MAD > 10%)
        # 邏輯：只要市場不是極致死魚盤 (MAD < 10%)，且動能出現，就追進去
        long_condition = (curr_mom > curr_mom_th) and (curr_mad > curr_mad_th)
        
        # 出場: 動能轉弱 (Mom < 70%) 且 市場變死魚 (MAD < 10%)
        # 邏輯：必須等到動能消失且波動率也躺平了才出場 (非常寬鬆的出場，容易抱大波段)
        exit_condition = (curr_mom < curr_mom_th) and (curr_mad < curr_mad_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'Mom_Strong({curr_mom:.2f}) & Not_Dead_Fish({curr_mad:.4f})'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'Mom_Weak & Vol_Dead'
            }
            
        return None