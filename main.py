import logging
from dotenv import load_dotenv
from utils.config_loader import ConfigLoader
from core.bot import TradingBot
import warnings

# 過濾掉 pytrends 引發的 FutureWarning
warnings.filterwarnings("ignore", category=FutureWarning, module="pytrends")
# 設定 Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("trading_bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def main():
    # 1. 載入環境變數
    load_dotenv()
    
    # 2. 載入設定
    config = ConfigLoader("config.json")
    
    # 3. 實例化機器人
    bot = TradingBot(config)
    
    # 4. 啟動
    bot.run()

if __name__ == "__main__":
    main()