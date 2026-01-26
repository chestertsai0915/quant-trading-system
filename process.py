import os
import pandas as pd
from dotenv import load_dotenv
from binance.um_futures import UMFutures
from binance.error import ClientError

# 1. 載入環境變數
load_dotenv()

api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_SECRET_KEY')

# 建立合約 Client 連線
# 如果是使用測試網 (Testnet)，需要加入 base_url='https://testnet.binancefuture.com'
# 這裡是正式網 (Mainnet)
client = UMFutures(key=api_key, secret=api_secret)

def check_futures_connection():
    print("--- 🚀 開始連線測試 (Binance Futures U-M) ---")
    
    try:
        # 2. 測試：獲取伺服器時間
        time_res = client.time()
        print(f"✅ 合約伺服器連線成功！Server Time: {time_res['serverTime']}")

        # 3. 測試：獲取 BTCUSDT 合約最新價格
        symbol = "BTCUSDT"
        price_info = client.ticker_price(symbol=symbol)
        print(f"📈 {symbol} 合約最新價格: {price_info['price']}")

        # 4. 測試：獲取合約帳戶餘額 (注意：合約的 endpoint 是 balance)
        print("\n🔍 正在讀取合約帳戶資產...")
        balances = client.balance()
        
        # 轉成 DataFrame 方便看
        df = pd.DataFrame(balances)
        # 只需要看 USDT 和 BNB (如果有用BNB抵扣手續費)
        # 欄位說明: balance(錢包餘額), availableBalance(可用下單餘額), crossWalletBalance(全倉餘額)
        target_assets = ['USDT', 'BNB']
        my_assets = df[df['asset'].isin(target_assets)].copy()
        
        if my_assets.empty:
            print("⚠️ 合約帳戶內沒有 USDT")
        else:
            print("💰 你的合約錢包資產：")
            print(my_assets[['asset', 'balance', 'availableBalance']].to_string(index=False))

        # 5. 測試：檢查當前持倉 (Position Risk)
        print("\n🔍 正在檢查當前持倉...")
        positions = client.get_position_risk(symbol=symbol)
        # 過濾掉沒有持倉的 (positionAmt != 0)
        open_positions = [p for p in positions if float(p['positionAmt']) != 0]
        
        if not open_positions:
            print(f"✅ 目前 {symbol} 無任何持倉 (空手)")
        else:
            print(f"⚠️ 偵測到 {symbol} 有持倉：")
            for p in open_positions:
                print(f"   方向: {'多單' if float(p['positionAmt']) > 0 else '空單'} | 數量: {p['positionAmt']} | 未實現盈虧: {p['unRealizedProfit']}")

    except ClientError as error:
        print(f"❌ API 錯誤: {error.error_message}")
        print(f"   (錯誤代碼: {error.error_code})")
        print("   👉 請檢查 API Key 是否有勾選 'Enable Futures' (允許合約)")
    except Exception as e:
        print(f"❌ 系統錯誤: {e}")

if __name__ == "__main__":
    check_futures_connection()