import requests
import os
from dotenv import load_dotenv
import json

# 載入環境變數
load_dotenv()

class TelegramTester:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        if not self.token:
            print("❌ 錯誤: 未在 .env 找到 TELEGRAM_BOT_TOKEN")
            return

        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def get_updates(self):
        """
        抓取機器人的更新紀錄 (用來找 Chat ID)
        """
        url = f"{self.base_url}/getUpdates"
        try:
            print(f"🔍 正在嘗試從 {url} 獲取更新...")
            response = requests.get(url, timeout=10)
            data = response.json()
            
            if data.get('ok'):
                results = data.get('result', [])
                if not results:
                    print("⚠️ 成功連線，但沒有收到任何訊息紀錄。")
                    print("👉 請去 Telegram 找到你的機器人，點擊 'Start' 或隨便傳一句話給它，然後再執行一次此程式。")
                else:
                    print("\n✅ 找到以下對話紀錄 (請尋找你的 ID):")
                    for update in results:
                        # 嘗試解析常見的訊息格式
                        message = update.get('message', {})
                        chat = message.get('chat', {})
                        user = message.get('from', {})
                        text = message.get('text', '(非文字訊息)')
                        
                        chat_id = chat.get('id')
                        username = user.get('username', 'Unknown')
                        
                        print(f"   - 來自: {username} | 內容: {text} | 👉 Chat ID: {chat_id}")
            else:
                print(f"❌ API 回傳錯誤: {data}")
                
        except Exception as e:
            print(f"❌ 連線失敗: {e}")

    def send_test_message(self):
        """
        發送測試訊息
        """
        if not self.chat_id:
            print("⚠️ 未設定 Chat ID，跳過發送測試。請先執行 get_updates() 來獲取 ID。")
            return

        url = f"{self.base_url}/sendMessage"
        payload = {
            'chat_id': self.chat_id,
            'text': "🚀 **Telegram Bot 測試成功！**\n這是一條來自 Python 的測試訊息。",
            'parse_mode': 'Markdown'
        }
        
        try:
            print(f"\n📤 正在發送測試訊息到 ID: {self.chat_id} ...")
            response = requests.post(url, json=payload, timeout=10)
            data = response.json()
            
            if data.get('ok'):
                print("✅ 發送成功！請檢查你的手機。")
            else:
                print(f"❌ 發送失敗: {data.get('description')}")
                print("   (常見原因: Chat ID 錯誤，或是你還沒對機器人按下 Start)")
                
        except Exception as e:
            print(f"❌ 發送過程發生錯誤: {e}")

if __name__ == "__main__":
    tester = TelegramTester()
    
    if tester.token:
        # 1. 先嘗試發送 (如果你已經填了 ID)
        tester.send_test_message()
        
        # 2. 如果發送失敗或沒填 ID，嘗試抓取更新來幫你找 ID
        print("\n--------------------------------------------------")
        print("🛠 正在執行 ID 診斷工具...")
        tester.get_updates()