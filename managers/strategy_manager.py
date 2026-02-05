import logging
from strategies.test_stratey2 import TestStrategy2
# from strategies.price_volume2 import PriceVolume2

class StrategyManager:
    def __init__(self):
        self.strategies = []
        self._register_strategies()

    def _register_strategies(self):
        """ 在這裡註冊你要跑的策略 """
        self.strategies = [
            TestStrategy2(),
            # PriceVolume2()
        ]
        logging.info(f"已掛載策略: {[s.name for s in self.strategies]}")

    def warm_up_all(self, history_df):
        """ 策略熱機 """
        if history_df.empty:
            logging.warning("無歷史數據，跳過熱機")
            return

        logging.info("開始策略熱機...")
        # 排除最後一根未收盤的
        history_closed = history_df.iloc[:-1]
        
        for strategy in self.strategies:
            try:
                strategy.warm_up(history_closed)
            except Exception as e:
                logging.error(f"策略 {strategy.name} 熱機失敗: {e}")
        logging.info("熱機完成")

    def generate_signals(self, strategy_df, external_data={}):
        """ 遍歷所有策略並產生訊號 """
       #未來必須改成多執行緒
        signals = []
        
        for strategy in self.strategies:
            strategy.update_data(strategy_df, external_data)
            signal = strategy.generate_signal()
            
            if signal:
                signals.append({
                    'strategy_name': strategy.name,
                    'action': signal['action'],
                    'reason': signal['reason'],
                    'ref_price': strategy_df['close'].iloc[-1]
                })
        
        return signals