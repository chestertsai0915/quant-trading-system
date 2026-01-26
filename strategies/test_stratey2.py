from .base_strategy import BaseStrategy

class TestStrategy2(BaseStrategy):
    def __init__(self):
        super().__init__(name="TEST_LOOP")
        # 設定一個開關，用來切換多空
        # True = 下一次發 LONG, False = 下一次發 CLOSE
        self.next_action_is_long = True

    def generate_signal(self):
        """
        產生訊號：一次買，一次賣，無限循環
        """
        if self.next_action_is_long:
            # --- 步驟 1: 發送開倉訊號 ---
            self.next_action_is_long = False # 切換開關，下次變成賣
            
            return {
                'action': 'LONG',
                'quantity': 0.005,  # 這裡的數量是參考用，RiskManager 會重算
                'reason': '強制測試 [開倉] 訊號'
            }
        else:
            # --- 步驟 2: 發送平倉訊號 ---
            self.next_action_is_long = True # 切換開關，下次變成買
            
            return {
                'action': 'CLOSE',
                'quantity': 0.0,    # 平倉時數量不重要，main.py 會自動讀取當前持倉全平
                'reason': '強制測試 [平倉] 訊號'
            }