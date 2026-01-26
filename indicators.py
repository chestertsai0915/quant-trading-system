import talib
import numpy as np
import pandas as pd
import pytz
from datetime import time as dt_time
import pywt

class AlphaLibrary:
    """
    通用因子計算庫
    """

    # ============================
    # 1. 基礎價量與波動率因子
    # ============================
    @staticmethod
    def calc_sma(data, window):
        """
        通用的 SMA 計算工具 (給策略判斷訊號用)
        """
        return talib.SMA(data, timeperiod=window)
    @staticmethod
    def calc_custom_atr(high, low, close, window):
        """ 自定義 ATR: TR 的 SMA (而非 Wilder's smoothing) """
        # 對應: max(h-l, |h-cp|, |l-cp|).rolling(16).mean()
        tr = talib.TRANGE(high, low, close)
        # fillna(0) 在 numpy 中對應 np.nan_to_num (但 talib 預設前幾根是 NaN，這裡保持 NaN 讓策略層決定，或依你的習慣填 0)
        ma_tr = talib.SMA(tr, timeperiod=window)
        return np.nan_to_num(ma_tr, nan=0)

    @staticmethod
    def calc_smooth_obv(close, volume, window):
        """ 平滑 OBV """
        # 對應: (vol * sign(diff)).cumsum().rolling(20).mean()
        # talib.OBV 邏輯與 cumsum(vol * sign(diff)) 完全一致
        raw_obv = talib.OBV(close, volume)
        smooth_obv = talib.SMA(raw_obv, timeperiod=window)
        return np.nan_to_num(smooth_obv, nan=0)

    @staticmethod
    def calc_bbw(close, timeperiod=20, nbdev=2):
        """ 布林通道寬度 (BBW) """
        # 對應: (upper - lower) / middle
        upper, middle, lower = talib.BBANDS(close, timeperiod=timeperiod, nbdevup=nbdev, nbdevdn=nbdev)
        # 避免分母為 0
        return np.divide((upper - lower), middle, out=np.zeros_like(middle), where=middle!=0)

    @staticmethod
    def calc_mad(data, window=10):
        """ 價格/成交量 偏離度 (MAD) """
        # 對應: (close - ma) / ma
        ma = talib.SMA(data, timeperiod=window)
        # 處理 NaN 和 分母為 0
        with np.errstate(divide='ignore', invalid='ignore'):
            mad = (data - ma) / ma
        return np.nan_to_num(mad, nan=0)

    @staticmethod
    def calc_vroc(volume, window=10):
        """ 成交量變化率 (VROC) """
        # 對應: (vol - vol_shift) / vol_shift
        # 這裡直接用 numpy shift 運算
        vol_shifted = np.roll(volume, window)
        vol_shifted[:window] = np.nan # 處理 shift 後的垃圾值
        
        with np.errstate(divide='ignore', invalid='ignore'):
            vroc = (volume - vol_shifted) / vol_shifted
        return np.nan_to_num(vroc, nan=0)

    # ============================
    # 2. 動量與微結構因子
    # ============================

    @staticmethod
    def calc_smooth_momentum(close, mom_period=10, smooth_period=5):
        """ 平滑動量 """
        # 對應: talib.MOM(10).rolling(5).mean()
        mom = talib.MOM(close, timeperiod=mom_period)
        smooth_mom = talib.SMA(mom, timeperiod=smooth_period)
        return np.nan_to_num(smooth_mom, nan=0)

    @staticmethod
    def calc_smooth_cci(high, low, close, cci_period=60, smooth_period=48):
        """ 平滑 CCI """
        # 對應: talib.CCI(60).rolling(48).mean()
        cci = talib.CCI(high, low, close, timeperiod=cci_period)
        smooth_cci = talib.SMA(cci, timeperiod=smooth_period)
        return np.nan_to_num(smooth_cci, nan=0)

    @staticmethod
    def calc_bs_ratio(high, low, close):
        """ 買賣壓比例 (BS Ratio) """
        # 對應: (close - low) / (high - close + 1e-9)
        buy_pressure = close - low
        sell_pressure = high - close
        
        return np.divide(buy_pressure, (sell_pressure + 1e-9))
    
    # ============================
    # 👇 新增：滾動分位數計算
    # ============================
    @staticmethod
    def calc_rolling_quantile(data, window, quantile):
        """
        計算滾動分位數
        input: numpy array or list
        output: numpy array (same length)
        """
        # Pandas 的 rolling quantile 實作最穩定
        s = pd.Series(data)
        # min_periods=1 確保剛開始數據不足時也有值 (雖然策略通常會 skip 前段)
        return s.rolling(window=window, min_periods=window).quantile(quantile).fillna(0).values
    # ============================
    # 運算工具
    # ============================
    @staticmethod
    def calc_difference(data, periods=1):
        """
        計算差分 (Difference)
        對應 pandas 的 .diff()
        """
        # 使用 numpy diff
        diff = np.diff(data, n=periods)
        # 為了保持長度一致，前面補 0 (或 NaN)
        # pandas diff 預設前面是 NaN，這裡我們補 0 以防計算出錯
        return np.concatenate((np.zeros(periods), diff))
    
    @staticmethod
    def calc_z_score(data, window):
        """
        計算 Z-Score (標準分數)
        Formula: (x - mean) / std
        """
        # 使用 Pandas Series 運算較方便
        s = pd.Series(data)
        z_score = (s - s.rolling(window).mean()) / s.rolling(window).std()
        return z_score.fillna(0).values

    # ============================
    # 3. 時間因子
    # ============================

    @staticmethod
    def add_us_market_open_flag(df_input):
        """
        時間因子: 判斷是否為美股開盤時間
        輸入: 含有 'timestamp' (datetime object) 的 DataFrame
        輸出: 新增 'is_trade_time' column 的 DataFrame
        """
        df = df_input.copy()
        
        # 確保 timestamp 是 datetime 格式 (如果是 int/str 需轉換)
        if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
             df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        eastern = pytz.timezone('US/Eastern')
        market_open = dt_time(9, 0)
        market_close = dt_time(16, 0)

        def is_open(utc_time):
            if pd.isnull(utc_time): return 0
            
            # 轉換時區
            if utc_time.tzinfo is None:
                utc_time = utc_time.replace(tzinfo=pytz.utc)
            us_time = utc_time.astimezone(eastern)

            # 週六日不交易
            if us_time.weekday() >= 5: return 0
            
            # 判斷時間
            return int(market_open <= us_time.time() <= market_close)

        df['is_trade_time'] = df['timestamp'].apply(is_open)
        return df
    # ============================
    # 4. 總經運算 (Macro)
    # ============================

    @staticmethod
    def calc_yield_spread(yield_long, yield_short):
        """
        計算殖利率利差 (例如 10Y - 2Y)
        """
        # 處理可能的缺失值 (0)
        if yield_long == 0 or yield_short == 0:
            return 0
        return yield_long - yield_short
    
    @staticmethod
    def calc_liquidity_change(current_assets, prev_assets):
        """
        (預留) 計算聯準會資產變化率
        """
        if prev_assets == 0: return 0
        return (current_assets - prev_assets) / prev_assets
    
    # ============================
    # 5. 頻域因子 (Frequency Domain)
    # ============================

    @staticmethod
    def calc_wavelet_features(data_window, wavelet='db4', level=3, mode='symmetric'):
        """
        對傳入的價格視窗進行小波轉換，提取特徵
        input: data_window (list or np.array, 長度建議 > 2^level, e.g., 120)
        output: dict 包含各層能量與均值
        """
        # 轉成 numpy array
        prices = np.array(data_window)
        
        # 小波分解
        try:
            coeffs = pywt.wavedec(prices, wavelet=wavelet, level=level, mode=mode)
        except Exception as e:
            # 如果數據長度不足以分解，回傳空字典
            return {}

        features = {}

        # 1. 處理 A 層 (近似層/低頻趨勢)
        approx = coeffs[0]
        features['A_mean'] = np.mean(approx)
        features['A_value'] = approx[-1]
        features['A_energy'] = np.sum(np.square(approx))

        # 2. 處理 D 層 (細節層/高頻噪音) -> 注意 wavedec 回傳順序是 [cA, cD3, cD2, cD1]
        # coeffs[1] 是最高層的 Detail (D3), coeffs[-1] 是 D1
        # 為了跟你原本的邏輯對應 (loop 1 to level)，我們依序處理
        
        # pywt 的 coeffs 結構: [cA_n, cD_n, cD_n-1, ..., cD_1]
        # 但你原本的 code 寫法: for i in range(1, level + 1): detail = coeffs[i]
        # PyWavelets 的 wavedec 回傳列表索引 1 對應的是 Level n 的 Detail
        
        for i in range(1, level + 1):
            detail = coeffs[i]
            # 建立特徵名稱: D1, D2, D3... (注意這裡 i=1 對應的是最深層的 Detail)
            # 通常 coeffs[1] 是 D3 (若 level=3)，coeffs[3] 是 D1
            # 這裡我們直接用索引命名，方便你對照
            layer_name = f"D{i}" 
            
            features[f'{layer_name}_mean'] = np.mean(detail)
            features[f'{layer_name}_value'] = detail[-1]
            features[f'{layer_name}_energy'] = np.sum(np.square(detail))

        return features