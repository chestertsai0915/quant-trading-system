import logging
import os
import pkgutil
import importlib
import inspect
from strategies.base_strategy import BaseStrategy 

class StrategyManager:
    def __init__(self, active_strategies=None):
        """
        :param active_strategies: (選填) 一個包含策略名稱字串的列表，例如 ['TestStrategy2', 'PriceVolume2']
                                  如果為 None，則預設載入所有掃描到的策略。
        """
        self.strategies = []
        self._strategy_classes = {} # 用來存 { "策略名": 類別物件 }
        
        # 1. 先掃描所有可用的策略類別
        self._scan_available_strategies()
        
        # 2. 根據設定檔 (或預設全部) 進行實例化
        self._register_strategies(active_strategies)

    def _scan_available_strategies(self):
        """ 自動掃描 strategies 資料夾下的所有策略類別 """
        # 取得 strategies 資料夾路徑
        current_dir = os.path.dirname(__file__)
        root_dir = os.path.dirname(current_dir)
        strategies_dir = os.path.join(root_dir, 'strategies')
        
        # 確保 strategies 模組能被 import
        if strategies_dir not in os.sys.path:
            os.sys.path.append(root_dir)

        # 走訪 strategies 資料夾內所有模組
        for _, module_name, _ in pkgutil.iter_modules([strategies_dir]):
            # 跳過 base_strategy 避免重複
            if module_name == 'base_strategy':
                continue
            
            try:
                # 動態 import 模組
                module = importlib.import_module(f"strategies.{module_name}")
                
                # 檢查模組內的所有屬性
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    
                    # 判斷條件：必須是繼承自 BaseStrategy 的類別，且不是 BaseStrategy 本身
                    if (inspect.isclass(attribute) and 
                        issubclass(attribute, BaseStrategy) and 
                        attribute is not BaseStrategy):
                        
                        # 註冊到字典中，Key 是類別名稱
                        self._strategy_classes[attribute.__name__] = attribute
                        # logging.debug(f"[SYSTEM] 掃描到可用策略: {attribute.__name__}")
                        
            except Exception as e:
                logging.error(f"[ERROR] 掃描策略模組 {module_name} 失敗: {e}")

    def _register_strategies(self, active_names):
        """ 實例化指定的策略 """
        self.strategies = []
        
        # 如果設定檔沒有指定策略 (None 或 Empty List)，則預設不做任何事，或者你可以改成載入全部
        if not active_names:
            logging.warning("未指定任何策略，目前無策略運行中。")
            return
        
        target_names = active_names 
        
        for name in target_names:
            strategy_cls = self._strategy_classes.get(name)
            if strategy_cls:
                try:
                    # 實例化策略
                    strategy_instance = strategy_cls()
                    self.strategies.append(strategy_instance)
                    logging.info(f"策略已掛載: {name}")
                except Exception as e:
                    logging.error(f"策略 {name} 實例化失敗: {e}")
            else:
                logging.warning(f"找不到名為 '{name}' 的策略類別，請檢查檔名或類別名稱。")

        logging.info(f"目前運行策略列表: {[s.name for s in self.strategies]}")

    def generate_signals(self, data_board):
        """ 
        遍歷所有策略並產生訊號 
        Input: data_board (包含 main_kline 與 external_data)
        """
        signals = []
        
        for strategy in self.strategies:
            try:
                # 1. 更新數據 (傳入 DataBoard)
                # BaseStrategy 會負責把 main_kline 拆出來給 strategy.kline_data
                strategy.update_data(data_board)
                
                # 2. 產生訊號
                signal = strategy.generate_signal()
                
                if signal:
                    # 取得目前參考價格 (用於日誌或計算)
                    ref_price = 0
                    if not data_board.main_kline.empty:
                        ref_price = data_board.main_kline['close'].iloc[-1]

                    # 補充策略名稱資訊
                    signal_data = {
                        'strategy_name': strategy.name,
                        'action': signal.get('action'),
                        'quantity': signal.get('quantity', 0), # 支援部分策略回傳 quantity
                        'reason': signal.get('reason', ''),
                        'ref_price': ref_price
                    }
                    signals.append(signal_data)
                    
            except Exception as e:
                logging.error(f"策略 {strategy.name} 產生訊號時發生錯誤: {e}")
        
        return signals