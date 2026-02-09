import pandas as pd
import os
from alpha_vantage.timeseries import TimeSeries
import requests
import logging
from .base_source import BaseDataSource

class USStockFetcher(BaseDataSource):
    name = "us_stock_qqq"
    def __init__(self):
        self.av_key = os.getenv('ALPHA_VANTAGE_KEY')
        self.tiingo_key = os.getenv('TIINGO_API_KEY')
        self.ts = TimeSeries(key=self.av_key, output_format='pandas') if self.av_key else None

    def fetch_data(self, symbol='QQQ', limit=100):
        """
        嘗試獲取美股數據
        策略：AlphaVantage -> (失敗) -> Tiingo
        """
        # 1. 嘗試 AlphaVantage (優先)
        df = self._fetch_alphavantage(symbol)
        if not df.empty:
            return df
            
        # 2. 嘗試 Tiingo (備用)
        if self.tiingo_key:
            logging.info(f"[US_STOCK] AlphaVantage 失敗，切換至備用源 Tiingo 抓取 {symbol}...")
            df = self._fetch_tiingo(symbol)
            if not df.empty:
                logging.info("[US_STOCK] Tiingo 抓取成功！")
                return df
        else:
            logging.warning("[US_STOCK] AlphaVantage 失敗且未設定 TIINGO_API_KEY，無法執行備援")

        return pd.DataFrame()

    def _fetch_alphavantage(self, symbol):
        """ AlphaVantage 實作 (保留您原本的邏輯) """
        try:
            if not self.ts:
                raise Exception("未設定 ALPHA_VANTAGE_KEY")

            # Alpha Vantage 每日額度有限，outputsize='compact' 只抓 100 筆
            data, meta = self.ts.get_daily(symbol=symbol, outputsize='compact')
            
            # 重命名欄位
            data = data.rename(columns={
                '1. open': 'open',
                '2. high': 'high',
                '3. low': 'low',
                '4. close': 'close',
                '5. volume': 'volume'
            })
            
            # 處理時間格式
            data.index = pd.to_datetime(data.index)
            df = data.reset_index()
            
            # AlphaVantage pandas format 的 index 名稱通常是 'date'
            col_map = {'date': 'open_time', 'index': 'open_time'}
            df.rename(columns=col_map, inplace=True)

            return self._format_df(df)

        except Exception as e:
            logging.warning(f"[AlphaVantage] 抓取失敗: {e}")
            return pd.DataFrame()

    def _fetch_tiingo(self, symbol):
        """ Tiingo 實作 (備用) """
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Token {self.tiingo_key}'
            }
            # Tiingo API: sort=-date 表示從新到舊，resampleFreq=daily
            url = f"https://api.tiingo.com/tiingo/daily/{symbol}/prices?resampleFreq=daily&sort=-date&token={self.tiingo_key}"
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
                
            data = response.json()
            if not data:
                return pd.DataFrame()

            df = pd.DataFrame(data)
            # Tiingo 回傳欄位: date, open, high, low, close, volume, adjClose...
            
            df['date'] = pd.to_datetime(df['date'])
            df.rename(columns={'date': 'open_time'}, inplace=True)
            
            return self._format_df(df)
            
        except Exception as e:
            logging.error(f"[Tiingo] 抓取失敗: {e}")
            return pd.DataFrame()

    def _format_df(self, df):
        """ 
        統一輸出格式
        確保符合 DatabaseHandler.save_market_data 的欄位要求 
        """
        # 確保 open_time 存在且格式正確
        if 'open_time' not in df.columns:
            return pd.DataFrame()

        # 將時間轉為毫秒 int (符合 DB 標準)
        if not pd.api.types.is_integer_dtype(df['open_time']):
             if pd.api.types.is_datetime64_any_dtype(df['open_time']):
                  df['open_time'] = df['open_time'].astype('int64') // 10**6
             else:
                  # 如果是字串，先轉 datetime 再轉 int
                  df['open_time'] = pd.to_datetime(df['open_time']).astype('int64') // 10**6

        required_cols = ['open_time', 'open', 'high', 'low', 'close', 'volume']
        
        # 確保數值型別為 float
        for col in required_cols:
            if col in df.columns and col != 'open_time':
                df[col] = df[col].astype(float)
        
        # 排序並只取最後 100 筆 (與 compact 邏輯一致)
        df = df.sort_values('open_time')
        
        # 加上通用外部數據需要的欄位 (為了相容性)
        # 這樣存入 DB 時如果走 save_generic_external_data 也不會報錯
        df['symbol'] = 'QQQ'
        df['metric'] = 'price'
        df['value'] = df['close']
        
        return df.tail(100)