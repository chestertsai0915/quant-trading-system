from .base_strategy import BaseStrategy
import pandas as pd

class PriceVolume1(BaseStrategy):
    def __init__(self):
        super().__init__()
        
        # --- 參數設定 (對應 Feature ID 的參數) ---
        self.mad_ma = 10       # MAD 的均線週期
        self.win = 25          # 滾動視窗
        self.th1 = 0.8         # MAD 閾值分位數
        self.th2 = 0.9         # BS 閾值分位數

    def generate_signal(self):
        
        # 1. 定義需要的特徵 ID (點菜單)
        
        
        # A. 數值本身
        fid_mad = f"mad_close_{self.mad_ma}_v1"  # 需確保 feature_definitions.py 有 MAD_V1 且 id 規則一致
        fid_bs  = "bs_ratio_v1"
        
        # B. 閾值線 (來自我們剛新增的複合特徵)
        fid_mad_th = f"mad_quantile_{self.mad_ma}_{self.win}_{self.th1}_v1"
        fid_bs_th  = f"bs_quantile_{self.win}_{self.th2}_v1"
        
        # C. 濾網
        fid_time = "is_us_trade_time_v1"

        
        # 2. 向 Feature Store 請求數據
       
        # 這會自動計算、快取並對齊所有特徵
        df = self.load_features([fid_mad, fid_bs, fid_mad_th, fid_bs_th, fid_time])
        
        # 安全檢查
        if df.empty or len(df) < 50:
            return None
        
        # 檢查欄位是否存在 (防止 ID 打錯或計算失敗)
        required_cols = [fid_mad, fid_bs, fid_mad_th, fid_bs_th, fid_time]
        if not all(col in df.columns for col in required_cols):
            return None

       
        # 3. 交易邏輯 (只剩下單純的比大小)
        
        
        # 取出最新一筆 (Current Step)
        curr = df.iloc[-1]
        
        curr_mad    = curr[fid_mad]
        curr_bs     = curr[fid_bs]
        curr_mad_th = curr[fid_mad_th]
        curr_bs_th  = curr[fid_bs_th]
        is_trade    = bool(curr[fid_time]) # 轉成布林值

        # 進場條件
        long_condition = (curr_mad > curr_mad_th) and \
                         (curr_bs > curr_bs_th) and \
                         (is_trade)

        # 出場條件
        exit_condition = ((curr_mad < curr_mad_th) or (curr_bs < curr_bs_th)) and \
                         (is_trade)

        # 回傳訊號
        if long_condition:
            return {
                'action': 'LONG',
                'quantity': 0.005,
                'reason': f'MAD({curr_mad:.4f})>Th({curr_mad_th:.4f}) & BS({curr_bs:.2f})>Th'
            }
            
        elif exit_condition:
            return {
                'action': 'CLOSE',
                'quantity': 0,
                'reason': f'MAD or BS fell below Threshold'
            }
            
        return None