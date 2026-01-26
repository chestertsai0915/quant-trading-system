import requests
import os
import logging
# 👇 新增這一行
from dotenv import load_dotenv

# 👇 在 class 定義之前，先執行載入
load_dotenv()
class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_message(self, message):
        """ 發送訊息到 Telegram """
        if not self.token or not self.chat_id:
            logging.warning("⚠️ Telegram Token 或 Chat ID 未設定，無法發送通知。")
            return

        try:
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                #'parse_mode': 'Markdown' # 支援粗體等格式
            }
            response = requests.post(self.base_url, json=payload, timeout=5)
            
            if response.status_code != 200:
                logging.error(f"❌ Telegram 發送失敗: {response.text}")
        except Exception as e:
            logging.error(f"❌ Telegram 連線錯誤: {e}")

# 方便外部直接調用
notifier = TelegramNotifier()

def send_tg_msg(msg):
    notifier.send_message(msg)