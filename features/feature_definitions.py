from abc import ABC, abstractmethod
import pandas as pd
import numpy as np
import talib
import pytz
import pywt
from datetime import time as dt_time
import re

# ==========================================
# 基礎特徵介面
# ==========================================
class BaseFeature(ABC):
    feature_prefix = "" 

    def __init__(self):
        pass

    @property
    @abstractmethod
    def feature_id(self):
        """ 特徵的唯一標識符 """
        pass

    @abstractmethod
    def compute(self, data_board) -> pd.Series:
        """ 核心計算邏輯 """
        pass
    
    @classmethod
    def from_id(cls, fid):
        """ 從 ID 還原實例 """
        prefix = cls.feature_prefix
        if not prefix:
             name = re.sub(r'_V\d+$', '', cls.__name__)
             s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
             prefix = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

        if not fid.startswith(prefix): return None
        if fid == prefix + "_v1": return cls()
        if not fid.startswith(prefix + "_"): return None

        try:
            content = re.sub(r'_v\d+$', '', fid)
            params_str = content[len(prefix)+1:] 
            if not params_str: return cls()

            args = params_str.split('_')
            typed_args = []
            for a in args:
                try:
                    val = float(a)
                    if val.is_integer(): val = int(val)
                    typed_args.append(val)
                except:
                    typed_args.append(a)
            return cls(*typed_args)
        except Exception:
            return None
#基礎k線
class RawKlineColumn(BaseFeature):
    """
    用來直接提取原始 K 線的 OHLCV 欄位
    攔截對應的 ID: 'open', 'high', 'low', 'close', 'volume'
    """
    feature_prefix = "raw_kline" # 只是為了符合介面規範，實際透過 from_id 攔截

    def __init__(self, column='close'):
        self.column = column

    @property
    def feature_id(self):
        # 直接回傳原始欄位名稱 (例如 'close')，不加後綴
        return self.column

    @classmethod
    def from_id(cls, fid):
        # 覆寫攔截邏輯：只要 ID 是這五個單字之一，就建立實例
        if fid in ['open', 'high', 'low', 'close', 'volume']:
            return cls(column=fid)
        return None

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.main_kline
        if df is None or df.empty: return pd.DataFrame()
        
        # 檢查欄位是否存在
        if self.column not in df.columns:
            return pd.DataFrame()
            
        return pd.DataFrame({
            'open_time': df['open_time'] if 'open_time' in df.columns else df.index,
            self.feature_id: df[self.column]
        })
# ==========================================
# 1. 基礎價量與波動率因子
# ==========================================

class SMA_V1(BaseFeature):
    feature_prefix = "sma"
    def __init__(self, window=20, column='close'):
        self.window = window
        self.column = column
    @property
    def feature_id(self): return f"sma_{self.window}_{self.column}_v1"

    def compute(self, data_board) -> pd.Series:
        df = data_board.main_kline
        if df is None or df.empty: return pd.Series()
        
        # 直接取 values 計算
        data = df[self.column].values.astype(float)
        res = talib.SMA(data, timeperiod=self.window)
        return pd.DataFrame({
            'open_time': df['open_time'],           # 取得索引中的時間
            self.feature_id: np.nan_to_num(res, nan=0)
            })

class CustomATR_V1(BaseFeature):
    feature_prefix = "custom_atr"
    def __init__(self, window=14):
        self.window = window
    @property
    def feature_id(self): return f"custom_atr_{self.window}_v1"

    def compute(self, data_board) -> pd.Series:
        df = data_board.main_kline
        if df is None or df.empty: return pd.Series()
        
        tr = talib.TRANGE(df['high'].values.astype(float), 
                          df['low'].values.astype(float), 
                          df['close'].values.astype(float))
        ma_tr = talib.SMA(tr, timeperiod=self.window)
        return pd.DataFrame({
            'open_time': df['open_time'],           # 取得索引中的時間
            self.feature_id: np.nan_to_num(ma_tr, nan=0)
        })

class CustomATR_MA_V1(BaseFeature):
    feature_prefix = "custom_atr_ma"
    def __init__(self, atr_window=16, ma_window=30):
        self.atr_window = atr_window
        self.ma_window = ma_window
    @property
    def feature_id(self): return f"custom_atr_ma_{self.atr_window}_{self.ma_window}_v1"

    def compute(self, data_board) -> pd.Series:
        df = data_board.main_kline
        if df is None or df.empty: return pd.Series()
        
        tr = talib.TRANGE(df['high'].values.astype(float), 
                          df['low'].values.astype(float), 
                          df['close'].values.astype(float))
        atr = talib.SMA(tr, timeperiod=self.atr_window)
        atr = np.nan_to_num(atr, nan=0)
        atr_ma = talib.SMA(atr, timeperiod=self.ma_window)
        return pd.DataFrame({
            'open_time': df['open_time'],           # 取得索引中的時間
            self.feature_id: np.nan_to_num(atr_ma, nan=0)
        })

class CustomATR_Quantile_V1(BaseFeature):
    feature_prefix = "custom_atr_quantile"
    def __init__(self, atr_window=16, rolling_window=25, quantile=0.9):
        self.atr_window = atr_window
        self.rolling_window = rolling_window
        self.quantile = quantile
    @property
    def feature_id(self): return f"custom_atr_quantile_{self.atr_window}_{self.rolling_window}_{self.quantile}_v1"

    def compute(self, data_board) -> pd.Series:
        df = data_board.main_kline
        if df is None or df.empty: return pd.Series()
        
        tr = talib.TRANGE(df['high'].values.astype(float), 
                          df['low'].values.astype(float), 
                          df['close'].values.astype(float))
        atr = talib.SMA(tr, timeperiod=self.atr_window)
        
        atr_series = pd.Series(np.nan_to_num(atr, nan=0), index=df.index)
        return pd.DataFrame({
            'open_time': df['open_time'],           # 取得索引中的時間
            self.feature_id: atr_series.rolling(window=self.rolling_window, min_periods=self.rolling_window).quantile(self.quantile).fillna(0)
        })

class SmoothOBV_V1(BaseFeature):
    feature_prefix = "smooth_obv"
    def __init__(self, window=20):
        self.window = window
    @property
    def feature_id(self): return f"smooth_obv_{self.window}_v1"

    def compute(self, data_board) -> pd.Series:
        df = data_board.main_kline
        if df is None or df.empty: return pd.DataFrame()
        
        raw_obv = talib.OBV(df['close'].values.astype(float), df['volume'].values.astype(float))
        smooth_obv = talib.SMA(raw_obv, timeperiod=self.window)
        return pd.DataFrame({
            'open_time': df['open_time'],           # 取得索引中的時間
            self.feature_id: np.nan_to_num(smooth_obv, nan=0)
        })

class SmoothOBV_MA_V1(BaseFeature):
    feature_prefix = "smooth_obv_ma"
    def __init__(self, obv_window=20, ma_window=5):
        self.obv_window = obv_window
        self.ma_window = ma_window
    @property
    def feature_id(self): return f"smooth_obv_ma_{self.obv_window}_{self.ma_window}_v1"

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.main_kline
        if df is None or df.empty: return pd.DataFrame()
        
        raw_obv = talib.OBV(df['close'].values.astype(float), df['volume'].values.astype(float))
        smooth_obv = talib.SMA(raw_obv, timeperiod=self.obv_window)
        smooth_obv = np.nan_to_num(smooth_obv, nan=0)
        obv_ma = talib.SMA(smooth_obv, timeperiod=self.ma_window)
        return pd.DataFrame({
            'open_time': df['open_time'],           # 取得索引中的時間
            self.feature_id: np.nan_to_num(obv_ma, nan=0)
        })

class SmoothOBV_Quantile_V1(BaseFeature):
    feature_prefix = "smooth_obv_quantile"
    def __init__(self, obv_window=20, rolling_window=90, quantile=0.3):
        self.obv_window = obv_window
        self.rolling_window = rolling_window
        self.quantile = quantile
    @property
    def feature_id(self): return f"smooth_obv_quantile_{self.obv_window}_{self.rolling_window}_{self.quantile}_v1"

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.main_kline
        if df is None or df.empty: return pd.DataFrame()
        
        raw_obv = talib.OBV(df['close'].values.astype(float), df['volume'].values.astype(float))
        smooth_obv = talib.SMA(raw_obv, timeperiod=self.obv_window)
        smooth_obv = np.nan_to_num(smooth_obv, nan=0)
        
        obv_series = pd.Series(smooth_obv, index=df.index)
        return pd.DataFrame({
            'open_time': df['open_time'],           # 取得索引中的時間
            self.feature_id: obv_series.rolling(window=self.rolling_window, min_periods=self.rolling_window).quantile(self.quantile).fillna(0)
        })

class MAD_V1(BaseFeature):
    feature_prefix = "mad" 
    def __init__(self, column='close', window=10):
        self.column = column
        self.window = window
    @property
    def feature_id(self): return f"mad_{self.column}_{self.window}_v1"
    
    @classmethod
    def from_id(cls, fid):
        if not fid.startswith("mad_"): return None
        parts = fid.replace("mad_", "").replace("_v1", "").split("_")
        if len(parts) == 2: return cls(column=parts[0], window=int(parts[1]))
        return None

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.main_kline
        if df is None or df.empty: return pd.DataFrame()
        
        data = df[self.column].values.astype(float)
        ma = talib.SMA(data, timeperiod=self.window)
        with np.errstate(divide='ignore', invalid='ignore'):
            mad = (data - ma) / ma
        return pd.DataFrame({
            'open_time': df['open_time'],           # 取得索引中的時間
            self.feature_id: np.nan_to_num(mad, nan=0)
        })

class MAD_Quantile_V1(BaseFeature):
    feature_prefix = "mad_quantile"
    def __init__(self, mad_window=10, rolling_window=25, quantile=0.8):
        self.mad_window = mad_window
        self.rolling_window = rolling_window
        self.quantile = quantile
    @property
    def feature_id(self): return f"mad_quantile_{self.mad_window}_{self.rolling_window}_{self.quantile}_v1"

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.main_kline
        if df is None or df.empty: return pd.DataFrame()
        
        close = df['close'].values.astype(float)
        ma = talib.SMA(close, timeperiod=self.mad_window)
        with np.errstate(divide='ignore', invalid='ignore'):
            mad = (close - ma) / ma
        mad_series = pd.Series(np.nan_to_num(mad, nan=0), index=df.index)
        return pd.DataFrame({
            'open_time': df['open_time'],           # 取得索引中的時間
            self.feature_id: mad_series.rolling(window=self.rolling_window, min_periods=self.rolling_window).quantile(self.quantile).fillna(0)
        })

class BSRatio_V1(BaseFeature):
    feature_prefix = "bs_ratio"
    def __init__(self): pass
    @property
    def feature_id(self): return "bs_ratio_v1"

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.main_kline
        if df is None or df.empty: return pd.DataFrame()
        
        close = df['close'].values.astype(float)
        high = df['high'].values.astype(float)
        low = df['low'].values.astype(float)
        
        buy_pressure = close - low
        sell_pressure = high - close
        res = np.divide(buy_pressure, (sell_pressure + 1e-9))
        return pd.DataFrame({
            'open_time': df['open_time'],           # 取得索引中的時間
            self.feature_id: np.nan_to_num(res, nan=0)
        })

class BSRatio_Quantile_V1(BaseFeature):
    feature_prefix = "bs_quantile"
    def __init__(self, rolling_window=25, quantile=0.9):
        self.rolling_window = rolling_window
        self.quantile = quantile
    @property
    def feature_id(self): return f"bs_quantile_{self.rolling_window}_{self.quantile}_v1"

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.main_kline
        if df is None or df.empty: return pd.DataFrame()
        
        close = df['close'].values.astype(float)
        high = df['high'].values.astype(float)
        low = df['low'].values.astype(float)
        
        buy_pressure = close - low
        sell_pressure = high - close
        bs_ratio = np.divide(buy_pressure, (sell_pressure + 1e-9))
        bs_series = pd.Series(bs_ratio, index=df.index)
        return pd.DataFrame({
            'open_time': df['open_time'],           # 取得索引中的時間
            self.feature_id: bs_series.rolling(window=self.rolling_window, min_periods=self.rolling_window).quantile(self.quantile).fillna(0)
        })

class VROC_V1(BaseFeature):
    feature_prefix = "vroc"
    def __init__(self, window=10):
        self.window = window
    @property
    def feature_id(self): return f"vroc_{self.window}_v1"

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.main_kline
        if df is None or df.empty: return pd.DataFrame()
        
        volume = df['volume'].values.astype(float)
        vol_shifted = np.roll(volume, self.window)
        vol_shifted[:self.window] = np.nan
        with np.errstate(divide='ignore', invalid='ignore'):
            vroc = (volume - vol_shifted) / vol_shifted
        return pd.DataFrame({
            'open_time': df['open_time'],           # 取得索引中的時間
            self.feature_id: np.nan_to_num(vroc, nan=0)
        })

class VROC_Quantile_V1(BaseFeature):
    feature_prefix = "vroc_quantile"
    def __init__(self, vroc_window=10, rolling_window=250, quantile=0.8):
        self.vroc_window = vroc_window
        self.rolling_window = rolling_window
        self.quantile = quantile
    @property
    def feature_id(self): return f"vroc_quantile_{self.vroc_window}_{self.rolling_window}_{self.quantile}_v1"

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.main_kline
        if df is None or df.empty: return pd.DataFrame()
        
        volume = df['volume'].values.astype(float)
        vol_shifted = np.roll(volume, self.vroc_window)
        vol_shifted[:self.vroc_window] = np.nan
        with np.errstate(divide='ignore', invalid='ignore'):
            vroc = (volume - vol_shifted) / vol_shifted
        
        vroc_series = pd.Series(np.nan_to_num(vroc, nan=0), index=df.index)
        return pd.DataFrame({
            'open_time': df['open_time'],           # 取得索引中的時間
            self.feature_id: vroc_series.rolling(window=self.rolling_window, min_periods=self.rolling_window).quantile(self.quantile).fillna(0)
        })

class SmoothMomentum_V1(BaseFeature):
    feature_prefix = "smooth_mom"
    def __init__(self, mom_period=10, smooth_period=5):
        self.mom_period = mom_period
        self.smooth_period = smooth_period
    @property
    def feature_id(self): return f"smooth_mom_{self.mom_period}_{self.smooth_period}_v1"

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.main_kline
        if df is None or df.empty: return pd.DataFrame()
        
        mom = talib.MOM(df['close'].values.astype(float), timeperiod=self.mom_period)
        smooth_mom = talib.SMA(mom, timeperiod=self.smooth_period)
        return pd.DataFrame({
            'open_time': df['open_time'],           # 取得索引中的時間
            self.feature_id: np.nan_to_num(smooth_mom, nan=0)
        })

class SmoothMomentum_Quantile_V1(BaseFeature):
    feature_prefix = "smooth_mom_quantile"
    def __init__(self, mom_period=10, smooth_period=5, rolling_window=25, quantile=0.7):
        self.mom_period = mom_period
        self.smooth_period = smooth_period
        self.rolling_window = rolling_window
        self.quantile = quantile
    @property
    def feature_id(self): return f"smooth_mom_quantile_{self.mom_period}_{self.smooth_period}_{self.rolling_window}_{self.quantile}_v1"

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.main_kline
        if df is None or df.empty: return pd.DataFrame()
        
        mom = talib.MOM(df['close'].values.astype(float), timeperiod=self.mom_period)
        smooth_mom = talib.SMA(mom, timeperiod=self.smooth_period)
        mom_series = pd.Series(np.nan_to_num(smooth_mom, nan=0), index=df.index)
        return pd.DataFrame({
            'open_time': df['open_time'],           # 取得索引中的時間
            self.feature_id: mom_series.rolling(window=self.rolling_window, min_periods=self.rolling_window).quantile(self.quantile).fillna(0)
        })

class IsUSTradeTime_V1(BaseFeature):
    feature_prefix = "is_us_trade_time"
    def __init__(self):
        self.eastern = pytz.timezone('US/Eastern')
        self.market_open = dt_time(9, 0)
        self.market_close = dt_time(16, 0)
    @property
    def feature_id(self): return "is_us_trade_time_v1"

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.main_kline
        if df is None or df.empty: return pd.DataFrame()

        def is_open(utc_time):
            if pd.isnull(utc_time): return 0
            # 這裡假設傳進來的是 Series 的值，通常是 timestamp (int/float)
            if isinstance(utc_time, (int, float)):
                 utc_time = pd.to_datetime(utc_time, unit='ms')
            if utc_time.tzinfo is None:
                utc_time = utc_time.replace(tzinfo=pytz.utc)
            us_time = utc_time.astimezone(self.eastern)
            if us_time.weekday() >= 5: return 0
            return int(self.market_open <= us_time.time() <= self.market_close)

        # 這裡需要注意：如果不確定時間在哪，先試著找 'open_time'
        if 'open_time' in df.columns:
            times = df['open_time']
        else:
            # 如果沒有 open_time column，就用 index (假設 index 是時間)
            times = df.index.to_series()
            
        result = times.apply(is_open)
        result.index = df.index
        return pd.DataFrame({
            'open_time': df['open_time'] if 'open_time' in df.columns else df.index,
            self.feature_id: result 
        })

# --- Raw Data Extractors (Minimal) ---

class GoogleTrendsRaw_V1(BaseFeature):
    feature_prefix = "google_trends_raw"
    def __init__(self, metric='google_trends_BTC'):
        self.metric = metric
    @property
    def feature_id(self): return f"google_trends_raw_{self.metric}_v1"
    
    @classmethod
    def from_id(cls, fid):
        if not fid.startswith("google_trends_raw_"): return None
        metric = fid.replace("google_trends_raw_", "").replace("_v1", "")
        return cls(metric=metric)

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.external_data.get('google_trends')
        if df is None or df.empty: return pd.DataFrame()
        
        target = df[df['metric'] == self.metric]
        if target.empty: return pd.DataFrame()
        
        # 假設外部數據有 open_time 欄位
        if 'open_time' in target.columns:
            df=pd.DataFrame({
            'open_time': target['open_time'] if 'open_time' in target.columns else target.index,
            self.feature_id: target["value"]
        })   
        return df

class FearGreedRaw_V1(BaseFeature):
    feature_prefix = "fear_greed_raw"
    @property
    def feature_id(self): return "fear_greed_raw_v1"
    
    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.external_data.get('fear_greed')
        if df is None or df.empty: return pd.DataFrame()
        
        if 'open_time' in df.columns:
            df=pd.DataFrame({
            'open_time': df['open_time'] if 'open_time' in df.columns else df.index,
            self.feature_id: df["value"]
        })   
        return df   
        
class MacroRaw_V1(BaseFeature):
    feature_prefix = "macro_raw"
    def __init__(self, metric='yield_10y'):
        self.metric = metric
    @property
    def feature_id(self): return f"macro_raw_{self.metric}_v1"
    
    @classmethod
    def from_id(cls, fid):
        if not fid.startswith("macro_raw_"): return None
        metric = fid.replace("macro_raw_", "").replace("_v1", "")
        return cls(metric=metric)

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.external_data.get('fred_macro')
        if df is None or df.empty: return pd.DataFrame()
        
        target = df[df['metric'] == self.metric]
        if target.empty: return pd.DataFrame()
        
        if 'open_time' in target.columns:
            df= pd.DataFrame({
            'open_time': target['open_time'] if 'open_time' in target.columns else target.index,
            self.feature_id: target["value"]
        })
        return df

class ZScore_V1(BaseFeature):
    feature_prefix = "zscore"
    def __init__(self, column='close', window=100):
        self.column = column
        self.window = window
    @property
    def feature_id(self): return f"zscore_{self.column}_{self.window}_v1"
    
    @classmethod
    def from_id(cls, fid):
        prefix = "zscore_"
        if not fid.startswith(prefix): return None
        parts = fid[len(prefix):].replace("_v1", "").split("_")
        if len(parts) == 2: return cls(column=parts[0], window=int(parts[1]))
        return None

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.main_kline
        if df is None or df.empty: return pd.DataFrame()
        
        series = df[self.column]
        z = (series - series.rolling(self.window).mean()) / series.rolling(self.window).std()
        return pd.DataFrame({
            'open_time': df['open_time'] if 'open_time' in df.columns else df.index,
            self.feature_id: z.fillna(0)})

class ZScore_Quantile_V1(BaseFeature):
    feature_prefix = "zscore_quantile"
    def __init__(self, z_window=100, rolling_window=1000, quantile=0.7):
        self.z_window = z_window
        self.rolling_window = rolling_window
        self.quantile = quantile
    @property
    def feature_id(self): return f"zscore_quantile_{self.z_window}_{self.rolling_window}_{self.quantile}_v1"

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.main_kline
        if df is None or df.empty: return pd.DataFrame()
        
        series = df['close']
        z = (series - series.rolling(self.z_window).mean()) / series.rolling(self.z_window).std()
        return pd.DataFrame({
            'open_time': df['open_time'] if 'open_time' in df.columns else df.index,
            self.feature_id: z.rolling(window=self.rolling_window, min_periods=self.rolling_window).quantile(self.quantile).fillna(0)
        })

class VolumeSMA_Diff_V1(BaseFeature):
    feature_prefix = "vol_sma_diff"
    def __init__(self, sma_window=15):
        self.sma_window = sma_window
    @property
    def feature_id(self): return f"vol_sma_diff_{self.sma_window}_v1"

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.main_kline
        if df is None or df.empty: return pd.DataFrame()
        
        vol = df['volume'].values.astype(float)
        sma = talib.SMA(vol, timeperiod=self.sma_window)
        # 這裡要注意，如果要 diff，最好轉回 Series
        sma_series = pd.Series(sma, index=df.index)
        return pd.DataFrame({
            'open_time': df['open_time'] if 'open_time' in df.columns else df.index,
            self.feature_id: sma_series.diff().fillna(0)
        })

class VolumeSMA_Diff_Quantile_V1(BaseFeature):
    feature_prefix = "vol_sma_diff_quantile"
    def __init__(self, sma_window=15, rolling_window=60, quantile=0.8):
        self.sma_window = sma_window
        self.rolling_window = rolling_window
        self.quantile = quantile
    @property
    def feature_id(self): return f"vol_sma_diff_quantile_{self.sma_window}_{self.rolling_window}_{self.quantile}_v1"

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.main_kline
        if df is None or df.empty: return pd.DataFrame()
        
        vol = df['volume'].values.astype(float)
        sma = talib.SMA(vol, timeperiod=self.sma_window)
        sma_series = pd.Series(sma, index=df.index)
        diff = sma_series.diff().fillna(0)
        
        return pd.DataFrame({
            'open_time': df['open_time'] if 'open_time' in df.columns else df.index,
            self.feature_id: diff.rolling(window=self.rolling_window, min_periods=self.rolling_window).quantile(self.quantile).fillna(0)
        })

class WaveletFeature_V1(BaseFeature):
    feature_prefix = "wavelet"
    def __init__(self, target_source='us_stock_qqq', window=120, output_col='A_mean'):
        self.target_source = target_source
        self.window = window
        self.output_col = output_col

    @property
    def feature_id(self):
        return f"wavelet_{self.target_source}_{self.window}_{self.output_col}_v1"
    
    @classmethod
    def from_id(cls, fid):
        if not fid.startswith("wavelet_"): return None
        if "us_stock_qqq" in fid:
            try:
                parts = fid.split("us_stock_qqq_")[1].replace("_v1", "").split("_", 1)
                return cls(target_source="us_stock_qqq", window=int(parts[0]), output_col=parts[1])
            except: return None
        return None

    def compute(self, data_board) -> pd.DataFrame:
        df = data_board.external_data.get(self.target_source)
        if df is None or df.empty: return pd.DataFrame()
        
            
        def calc_single_window(window_data):
            if len(window_data) < 8: return 0 
            try:
                coeffs = pywt.wavedec(window_data, wavelet='db4', level=3, mode='symmetric')
                if self.output_col == 'A_mean': return np.mean(coeffs[0])
                return 0
            except: return 0

        res = df['close'].rolling(window=self.window).apply(calc_single_window, raw=True)
        return pd.DataFrame({
            'open_time': df.index,
            self.feature_id: res
        })