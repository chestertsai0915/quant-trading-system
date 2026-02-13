from .base_strategy import BaseStrategy
import pandas as pd

class PriceVolume3(BaseStrategy):
    def __init__(self):
        super().__init__(name="Strategy3_MAD_OBV_Quantile")
        
        # --- 參數映射 ---
        self.mad_period = 10   # MAD 計算本身需要的週期
        self.obv_smooth = 20   # OBV 平滑週期
        
        self.window = 90       # 滾動視窗 (用於計算閾值)
        self.th1 = 0.9         # MAD 閾值 (前 10% 高)
        self.th2 = 0.3         # OBV 閾值 (高於後 30%)

    def generate_signal(self):
        # ==========================================
        # 1. 定義需要的特徵 ID (點菜)
        # ==========================================
        
        # A. 基礎指標數值
        # 這裡假設你的 MAD_V1 定義是 mad_{column}_{window}_v1
        fid_mad = f"mad_close_{self.mad_period}_v1"
        fid_obv = f"smooth_obv_{self.obv_smooth}_v1"
        
        # B. 動態閾值線 (Rolling Quantile)
        # MAD 的 90% 分位數線 (使用 PriceVolume1 定義過的 MAD_Quantile)
        fid_mad_th = f"mad_quantile_{self.mad_period}_{self.window}_{self.th1}_v1"
        
        # OBV 的 30% 分位數線 (使用剛剛新增的 SmoothOBV_Quantile)
        fid_obv_th = f"smooth_obv_quantile_{self.obv_smooth}_{self.window}_{self.th2}_v1"

        # ==========================================
        # 2. 向 Feature Store 請求數據
        # ==========================================
        df = self.load_features([fid_mad, fid_obv, fid_mad_th, fid_obv_th])
        
        # 安全檢查
        if df.empty or len(df) < self.window + 20:
            return None

        required_cols = [fid_mad, fid_obv, fid_mad_th, fid_obv_th]
        if not all(col in df.columns for col in required_cols):
            return None

        # ==========================================
        # 3. 交易邏輯
        # ==========================================
        
        curr = df.iloc[-1]
        
        # 取值
        curr_mad    = curr[fid_mad]
        curr_obv    = curr[fid_obv]
        curr_mad_th = curr[fid_mad_th]
        curr_obv_th = curr[fid_obv_th]

        # 決策邏輯 (MAD 突破高標 且 OBV 維持水準)
        long_condition = (curr_mad > curr_mad_th) and (curr_obv > curr_obv_th)
        
        # 出場 (MAD 冷卻 或 OBV 轉弱)
        exit_condition = (curr_mad < curr_mad_th) or (curr_obv < curr_obv_th)

        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'MAD_Breakout({curr_mad:.4f}) & OBV_Healthy'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'MAD_CoolDown or OBV_Weak'
            }
            
        return None