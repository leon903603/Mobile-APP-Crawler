from __future__ import annotations
import os

def load_env(env_path: str | None = None) -> None:
    """
    輕量級自動載入 .env 檔案中的環境變數 (不依賴外部三方套件)。
    若系統已有該變數，則以系統變數為優先。
    """
    if not env_path:
        # 預設尋找專案根目錄下的 .env
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

    if not os.path.exists(env_path):
        return

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    # 不覆蓋系統既有的環境變數
                    if key not in os.environ:
                        os.environ[key] = val
    except Exception as e:
        print(f"[WARN] Failed to load .env from {env_path}: {e}")

# 自動載入
load_env()

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 5433)),
    "database": os.environ.get("DB_NAME", "appcrawler"),
    "user": os.environ.get("DB_USER", "crawler"),
    "password": os.environ.get("DB_PASS", "crawlerpass")
}