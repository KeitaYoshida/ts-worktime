import json
from tkinter import messagebox

CONFIG_FILE = "config.json"

# デフォルト設定
default_config = {
    "server_helth_api": "http://192.168.13.30:8000/api/helth",
    "user_list_api": "http://192.168.13.30:8000/api/user/list-low",
    "set_timestamp_api": "http://192.168.13.30:8000/api/set/timestamp",
    "user_data_file": "user_data.json",
    "set_user_serial": "http://192.168.13.30:8000/api/user/update"
    # 必要に応じてここに他のデフォルト設定を追加
}


def load_config():
    """設定を読み込む"""
    try:
        with open(CONFIG_FILE, "r") as f:
            user_config = json.load(f)
    except FileNotFoundError:
        user_config = {}
    # default_config に user_config をマージして不足分を補う
    config = {**default_config, **user_config}
    return config


def save_config(config):
    """設定を保存する"""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)
    messagebox.showinfo("保存完了", "設定が保存されました。")