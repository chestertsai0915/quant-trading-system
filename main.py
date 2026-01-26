import time
import os
import logging
import traceback
from dotenv import load_dotenv

# Binance SDK
from binance.um_futures import UMFutures
from binance.error import ClientError

# 模組引入
from data_loader import DataLoader
from utils.notifier import send_tg_msg
from utils.database import DatabaseHandler
from utils.config_loader import ConfigLoader # 引入新模組

# Execution 模組
from execution.risk_manager import RiskManager
from execution.binance_executor import BinanceExecutor
from execution.mock_executor import MockExecutor

# 策略引入
from strategies.price_volume2 import PriceVolume2
from strategies.test_strategy import TestStrategy
from strategies.test_stratey2 import TestStrategy2

IS_PAPER_TRADING = False  # 全域變數，標示是否為模擬盤


# 設定 Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("trading_bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

load_dotenv()

class TradingBot:
    def __init__(self, config_file="config.json"):
        self.config_loader = ConfigLoader(config_file)
        
        # 從 Config 讀取參數
        self.symbol = self.config_loader.get("trading", "symbol", "BTCUSDT")
        self.interval = self.config_loader.get("trading", "interval", "1h")
        self.mode = self.config_loader.get("system", "mode", "TESTNET")
        self.is_paper = self.config_loader.get("system", "paper_trading", False)
        
        # Risk 參數
        leverage = self.config_loader.get("risk", "leverage", 1)
        fixed_amount = self.config_loader.get("risk", "fixed_amount", 20)
        
        # 2. 初始化連線
        self._init_clients()
        
        # 3. 初始化模組
        self.risk_manager = RiskManager(fixed_usdt_amount=fixed_amount, leverage=leverage)
        self.db = DatabaseHandler("trading_data.db")
        
        # 根據 Config 決定執行器
        if self.is_paper:
            self.executor = MockExecutor()
            logging.warning(" [MODE] 啟動 Paper Trading 模式")
        else:
            self.executor = BinanceExecutor(self.trade_client)
            if self.mode == "TESTNET":
                logging.warning("[MODE] 啟動 Testnet 測試網模式")
            else:
                logging.warning(" [MODE] 啟動 Real Money 實盤模式")

    def _init_clients(self):
        """ 初始化 API 客戶端 """
        real_key = os.getenv('BINANCE_API_KEY')
        real_secret = os.getenv('BINANCE_SECRET_KEY')
        test_key = os.getenv('TESTNET_API_KEY')
        test_secret = os.getenv('TESTNET_SECRET_KEY')

        try:
            # Data Client (永遠連真實主網)
            self.data_client = UMFutures(key=real_key, secret=real_secret)
            self.data_loader = DataLoader(self.data_client)
            logging.info(" 數據源連線成功 (Real Market)")
        except Exception as e:
            logging.error(f" 數據源連線失敗: {e}")
            raise e

        # Trade Client (根據設定選擇)
        if self.mode == "TESTNET":
            self.trade_client = UMFutures(
                key=test_key, secret=test_secret, base_url='https://testnet.binancefuture.com'
            )
        else:
            self.trade_client = UMFutures(key=real_key, secret=real_secret)

    def register_strategies(self):
        """ 註冊要運行的策略 """
        self.strategies = [
            # PriceVolume2(),
            TestStrategy2()
        ]
        logging.info(f" 已載入策略: {[s.name for s in self.strategies]}")

    def initialize(self):
        """ 啟動前的準備工作：設定槓桿、Warm-up """
        send_tg_msg(f" **機器人啟動**\n監控: `{self.symbol}`\n模式: {'Testnet' if self.mode == 'TESTNET' else 'Real'}")
        
        # 1. 設定槓桿
        
        leverage = self.config_loader.get("risk", "leverage", 1)
        logging.info(f" 同步交易所槓桿: {leverage}x")
        self.executor.set_leverage(self.symbol, leverage)
        
        # 2. 策略熱機
        logging.info(" 開始策略熱機 (Warm-up)...")
        try:
            history_df = self.data_loader.get_binance_klines(self.symbol, self.interval, limit=1500)
            if not history_df.empty:
                for strategy in self.strategies:
                    strategy.warm_up(history_df)
                logging.info(" 熱機完成")
            else:
                logging.warning(" 熱機失敗：無歷史數據")
        except Exception as e:
            logging.error(f" 熱機錯誤: {e}")

    def log_snapshot(self, price):
        """ 紀錄資產快照 """
        details = self.executor.get_position_details(self.symbol)
        if details:
            amt = details['amt']
            if abs(amt) > 0:
                logging.info(f" [SNAPSHOT] {self.symbol} | 持倉: {amt} | 均價: {details['entryPrice']} | PnL: {details['unRealizedProfit']} U")
            else:
                logging.info(f" [SNAPSHOT] {self.symbol} | 空手 | 現價: {price}")
        return details['amt'] if details else 0.0

    def _execute_trade_flow(self, strategy_name, action, quantity, current_price):
        """
        核心交易流程：下單 -> 等待 -> 查證 -> 紀錄
        這是將「執行」與「紀錄」分開的關鍵實作
        """
        # 1. 執行 (Execution)
        side = 'BUY' if action == 'LONG' else 'SELL'
        is_reduce = (action == 'CLOSE')
        
        # 發送訂單 (只拿 Order ID)
        response = self.executor.execute_order(
            self.symbol, side, quantity, reduce_only=is_reduce, market_price=current_price
        )
        
        if not response:
            return # 下單失敗，直接結束

        order_id = response.get('orderId')
        logging.info(f" 訂單已送出 (ID: {order_id})，等待撮合...")

        # 2. 等待 (Wait) - 給撮合引擎時間
        time.sleep(3) # 建議 2-3 秒

        # 3. 查證 (Verification) - 獲取真實成交資訊
        final_record = None
        
        if IS_PAPER_TRADING:
            # 模擬盤：直接用回傳值 (因為查不到)
            final_record = {
                'avgPrice': float(response.get('cumQuote', 0)) / float(response.get('executedQty', 1)),
                'executedQty': float(response.get('executedQty', 0)),
                'notional': float(response.get('cumQuote', 0)),
                'status': 'FILLED (Mock)'
            }
        else:
            # 實盤/Testnet：呼叫 API 查詢
            # 注意：這裡使用 fetch_order_status (內部應呼叫 query_order)
            final_record = self.executor.fetch_order_status(self.symbol, order_id)

        # 4. 紀錄 (Logging)
        if final_record and final_record['executedQty'] > 0:
            avg_price = final_record['avgPrice']
            qty = final_record['executedQty']
            
            # 寫入資料庫
            self.db.log_trade(
                strategy=strategy_name,
                symbol=self.symbol,
                side=action,
                price=avg_price,
                quantity=qty,
                order_id=str(order_id),
                notional=final_record['notional']
            )
            
            # 發送通知
            
            send_tg_msg(f" [成交確認] {action} {self.symbol}\n策略: {strategy_name}\n數量: {qty}\n均價: {avg_price:.2f}")
            logging.info(f" [VERIFIED] 訂單確認完成 | 均價: {avg_price}")
        else:
            logging.warning(f" 訂單 {order_id} 查證失敗或未成交")

    def run(self):
        """ 主迴圈 """
        self.initialize()
        
        while True:
            try:
                logging.info("----------------------------------------------------")
                
                # A. 數據更新
                df = self.data_loader.get_binance_klines(self.symbol, self.interval, limit=200)
                current_price = df['close'].iloc[-1]
                external_data = {}

                # B. 資產快照與持倉檢查
                current_pos_amt = self.log_snapshot(current_price)

                # C. 策略遍歷
                for strategy in self.strategies:
                    strategy.update_data(df, external_data)
                    signal = strategy.generate_signal()

                    if signal:
                        action = signal['action']
                        reason = signal['reason']
                        
                        # 記錄訊號
                        
                        logging.info(f" [SIGNAL] {strategy.name} | {action} | {reason}")
                        self.db.log_signal(strategy.name, self.symbol, action, current_price, reason)

                        # D. 交易決策
                        target_qty = 0
                        should_trade = False

                        if action == 'LONG':
                            if current_pos_amt > 0:
                                logging.info(f" [SKIP] {strategy.name} 喊多，但已有持倉")
                            else:
                                target_qty = self.risk_manager.calculate_quantity(current_price)
                                should_trade = True

                        elif action == 'CLOSE':
                            if current_pos_amt > 0:
                                target_qty = abs(current_pos_amt)
                                should_trade = True
                            else:
                                # logging.info(f" [SKIP] {strategy.name} 喊平，但空手")
                                pass

                        # E. 執行交易流程
                        if should_trade and target_qty > 0:
                            self._execute_trade_flow(strategy.name, action, target_qty, current_price)

                # 休息
                time.sleep(10)

            except KeyboardInterrupt:
                logging.warning(" 用戶手動停止")
                break
            except Exception as e:
                logging.error(f" [SYSTEM ERROR] 主迴圈崩潰: {e}", exc_info=True)
                send_tg_msg(f" **系統異常**: `{str(e)}`")
                time.sleep(30)

if __name__ == "__main__":
    bot = TradingBot()
    bot.register_strategies()
    bot.run()