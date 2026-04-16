import logging
from pathlib import Path

# ログ設定
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

def setup_logger(name="worktime"):
    """
    アプリケーション全体で使用するロガーを設定
    """
    logger = logging.getLogger(name)
    
    # 既存のハンドラがある場合は全て削除
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    logger.setLevel(logging.DEBUG)

    # ファイルハンドラ
    file_handler = logging.FileHandler(LOG_DIR / "worktime.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)

    # コンソールハンドラ
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

# デフォルトのロガーを設定
logger = setup_logger() 