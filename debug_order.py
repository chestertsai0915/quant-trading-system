import os
import json
import time
from dotenv import load_dotenv
from binance.um_futures import UMFutures
from binance.error import ClientError

# 載入環境變數
load_dotenv()

def debug_order_structure():
    # 1. 設定連線 (使用 Testnet 以策安全)
    key = os.getenv('TESTNET_API_KEY')
    secret = os.getenv('TESTNET_SECRET_KEY')
    
    if not key or not secret:
        print(" 錯誤: 請在 .env 設定 TESTNET_API_KEY 與 SECRET")
        return

    client = UMFutures(
        key=key, 
        secret=secret, 
        base_url='https://testnet.binancefuture.com',
        timeout=60  #  允許等待 60 秒
    )
    symbol = 'BTCUSDT'

    try:
        print("------------------------------------------------------")
        print("1. 正在發送測試訂單 (Market Buy 0.002 BTC)...")
        # 下一張市價單
        my_id = "bot_trade_001"
        order_response = client.new_order(
            symbol=symbol,
            side='BUY',
            type='MARKET',
            quantity=0.002,
            newClientOrderId=my_id
        )
        order_id = order_response['orderId']
        print(f" 下單成功! Order ID: {order_id}")
        
        # 稍等一下讓後端撮合與寫入資料庫
        print("等待 2 秒讓資料寫入...")
        time.sleep(2)

        print("------------------------------------------------------")
        print("2. 呼叫 query_order (查詢訂單詳情)...")
        # 這是你想驗證的重點
        order_info = client.query_order(symbol=symbol, orderId=order_id)
        
        # 🖨️ 印出漂亮的 JSON
        print(json.dumps(order_info, indent=4))

        print("\n [觀察重點]:")
        print(f"   - status: {order_info.get('status')}")
        print(f"   - executedQty (成交量): {order_info.get('executedQty')}")
        print(f"   - cumQuote (成交額): {order_info.get('cumQuote')}")
        print(f"   -  找找看有沒有 'fee' 或 'commission'? (通常是沒有的)")

        print("------------------------------------------------------")
        print("3. 呼叫 get_account_trades (查詢成交明細)...")
        # 這是找手續費的地方
        trades = client.get_account_trades(symbol=symbol, orderId=order_id)
        
        #  印出漂亮的 JSON
        print(json.dumps(trades, indent=4))
        
        if trades:
            fee = trades[0].get('commission')
            asset = trades[0].get('commissionAsset')
            print(f"\n [找到手續費了]: {fee} {asset}")

    except ClientError as error:
        print(f" 發生錯誤: {error.error_message}")
    except Exception as e:
        print(f" 未知錯誤: {e}")
if __name__ == "__main__":
    debug_order_structure()