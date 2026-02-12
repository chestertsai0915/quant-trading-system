import os
import time
import logging
import traceback
from binance.um_futures import UMFutures
from utils.database import DatabaseHandler
from utils.notifier import send_tg_msg
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
        
        send_tg_msg(f"**機器人啟動**\nSymbol: {self.symbol}\nMode: {self.mode}")

    def _init_clients(self):
        real_key = os.getenv('BINANCE_API_KEY')
        real_secret = os.getenv('BINANCE_SECRET_KEY')
        
        data_client = UMFutures(key=real_key, secret=real_secret)
        
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
                # 智慧睡眠邏輯
                current_time = time.time()
                seconds = time.localtime(current_time).tm_sec
                sleep_time = 0.3 if (seconds >= 57 or seconds <= 12) else 10
                
                # 1. 詢問 Data Manager
                is_new, closed_time, df_to_save = self.data_manager.check_new_candle()
                
                if is_new:
                    # 2. ETL 流程 -> 取得 DataBoard (而非大表)
                    data_board = self.data_manager.update_etl_process(closed_time, df_to_save)
                    
                    if data_board and not data_board.main_kline.empty:
                        
                        # 3. Strategy Manager 計算訊號 (傳入 data_board)
                        signals = self.strategy_manager.generate_signals(data_board)
                        
                        # 4. Trade Manager 執行交易
                        for signal in signals:
                            self.trade_manager.process_signal(signal, current_pos_amt=0)

                        ref_price = data_board.main_kline['close'].iloc[-1]
                        self.trade_manager.log_snapshot(ref_price)
                    
                    logging.info("本週期結束，等待下一次收盤...")
                
                time.sleep(sleep_time)

            except KeyboardInterrupt:
                logging.warning("停止運行")
                break
            except Exception as e:
                logging.error(f"核心崩潰: {e}")
                traceback.print_exc()
                time.sleep(30)