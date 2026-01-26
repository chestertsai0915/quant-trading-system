import json
import os
import logging

class ConfigLoader:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self._config = {}
        self.load_config()

    def load_config(self):
        """ 讀取 JSON 設定檔 """
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f" 找不到設定檔: {self.config_path}")

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
            logging.info(f"設定檔載入成功: {self.config_path}")
        except Exception as e:
            raise ValueError(f" 設定檔格式錯誤: {e}")

    def get(self, section, key, default=None):
        """ 安全地獲取參數 (支援兩層結構) """
        try:
            return self._config.get(section, {}).get(key, default)
        except Exception:
            return default