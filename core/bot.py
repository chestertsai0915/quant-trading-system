import os
import time
import logging
import traceback
from binance.um_futures import UMFutures
from utils.database import DatabaseHandler
from utils.notifier import send_tg_msg

# 引入三大經理
from managers import DataManager, StrategyManager, TradeManager

class TradingBot:
    def __init__(self, config_loader):
        self.config = config_loader
        self.symbol = self.config.get("trading", "symbol", "BTCUSDT")
        self.interval = self.config.get("trading", "interval", "1h")
        self.mode = self.config.get("system", "mode", "TESTNET")
        self.is_paper = self.config.get("system", "paper_trading", False)
        
        # 1. 初始化基礎設施
        self.db = DatabaseHandler("trading_data.db")
        self.data_client, self.trade_client = self._init_clients()
        strategy_names = self.config.get('trading','strategies', [])
        
        # 2. 初始化三大經理
        self.data_manager = DataManager(self.data_client, self.db, self.symbol, self.interval)
        self.strategy_manager = StrategyManager(strategy_names)
        self.trade_manager = TradeManager(self.trade_client, self.db, self.config, self.symbol, self.is_paper)
        
        # 3. 策略熱機
        history_df = self.data_manager.get_history_klines()
        self.strategy_manager.warm_up_all(history_df)
        
        send_tg_msg(f"**機器人啟動**\nSymbol: {self.symbol}\nMode: {self.mode}\nPaper: {self.is_paper}")

    def _init_clients(self):
        """ 建立 API 連線 """
        real_key = os.getenv('BINANCE_API_KEY')
        real_secret = os.getenv('BINANCE_SECRET_KEY')
        
        # Data Client (永遠連實盤)
        data_client = UMFutures(key=real_key, secret=real_secret)
        
        # Trade Client
        if self.mode == "TESTNET":
            trade_client = UMFutures(
                key=os.getenv('TESTNET_API_KEY'), 
                secret=os.getenv('TESTNET_SECRET_KEY'), 
                base_url='https://testnet.binancefuture.com'
            )
        else:
            trade_client = UMFutures(key=real_key, secret=real_secret)
            
        return data_client, trade_client

    def run(self):
        logging.info(f"監控 {self.interval} K 線...")
        
        while True:
            try:
                # 1. 詢問 Data Manager：有新 K 線嗎？
                is_new, closed_time, df_to_save = self.data_manager.check_new_candle()
                
                if is_new:
                    # 2. 執行 ETL 流程，並取得準備好的策略數據
                    strategy_df = self.data_manager.update_etl_process(closed_time, df_to_save)
                    
                    if not strategy_df.empty:
                        # 3. Trade Manager 報告目前持倉
                        # 使用上一根收盤價作為參考價
                        ref_price = strategy_df['close'].iloc[-1]
                        current_pos = self.trade_manager.log_snapshot(ref_price)
                        
                        # 4. Strategy Manager 計算訊號
                        signals = self.strategy_manager.generate_signals(strategy_df)
                        
                        # 5. Trade Manager 執行交易
                        for signal in signals:
                            self.trade_manager.process_signal(signal, current_pos)
                    
                    logging.info("本週期結束，等待下一次收盤...")
                
                time.sleep(10)

            except KeyboardInterrupt:
                logging.warning("停止運行")
                break
            except Exception as e:
                logging.error(f"核心崩潰: {e}")
                traceback.print_exc()
                time.sleep(30)