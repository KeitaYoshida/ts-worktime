import sqlite3
import requests
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from smartcard.scard import *
import smartcard.util
import signal
import sys
import threading
import time
import json
import os

# パスを絶対パスに変更
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(ROOT_DIR, "config.json")
DB_FILE = os.path.join(ROOT_DIR, "attendance.db")
API_BASE_URL = "http://localhost/api"

# デフォルト設定
DEFAULT_CONFIG = {
    "server_helth_api": "http://192.168.13.103:8000/api/helth",
    "user_list_api": "http://192.168.13.103:8000/api/user/list-low",
    "set_timestamp_api": "http://192.168.13.103:8000/api/set/timestamp",
    "user_data_file": "user_data.json",
    "set_user_serial": "http://192.168.13.103:8000/api/user/update",
    "marge_api": "http://192.168.13.103:8000/api/attendance/marge"
}

def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            user_config = json.load(f)
    except FileNotFoundError:
        print(f"設定ファイルが見つかりません: {CONFIG_FILE}")
        user_config = {}
    
    # デフォルト設定とマージ
    config = {**DEFAULT_CONFIG, **user_config}
    return config

def initialize_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS users")
    cursor.execute("""
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        res_user_id TEXT UNIQUE,
        name TEXT,
        login_id TEXT,
        id_serial TEXT
    )
    """)
    conn.commit()
    conn.close()


def insert_user_data(user_data):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    for user in user_data:
        cursor.execute("""
        INSERT OR IGNORE INTO users (res_user_id, name, login_id, id_serial)
        VALUES (?, ?, ?, ?)
        """, (user.get("id"), user.get("name"), user.get("loginid"), user.get("id_serial")))
    conn.commit()
    conn.close()

def fetch_user_data(config):
    try:
        response = requests.get(config['user_list_api'])
        if response.status_code == 200:
            user_data = response.json()
            insert_user_data(user_data)
        else:
            print("ユーザー情報の取得に失敗しました")
    except requests.RequestException as e:
        print(f"エラー: {e}")

def send_user_event(config, user_id, serial_number):
    endpoint = f"{config['set_user_serial']}/{user_id}"
    payload = {"serial": serial_number}
    try:
        response = requests.post(endpoint, json=payload)
        if response.status_code == 200:
            print("ユーザー情報の送信に成功しました")
        else:
            print(f"ユーザー情報の送信に失敗しました: {response.status_code}")
    except requests.RequestException as e:
        print(f"送信エラー: {e}")

def update_user_serial(serial_number, user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE users SET id_serial = ? WHERE res_user_id = ?
    """, (serial_number, user_id))
    conn.commit()
    conn.close()

def get_users():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT res_user_id, name, login_id FROM users")
    users = cursor.fetchall()
    conn.close()
    return users

def initialize_context():
    hresult, context = SCardEstablishContext(SCARD_SCOPE_USER)
    if hresult != SCARD_S_SUCCESS:
        raise Exception(f"コンテキストの確立に失敗しました: {SCardGetErrorMessage(hresult)}")
    return context

def list_readers(context):
    hresult, readers = SCardListReaders(context, [])
    if hresult != SCARD_S_SUCCESS:
        raise Exception(f"リーダーの取得に失敗しました: {SCardGetErrorMessage(hresult)}")
    return readers

def create_gui():
    root = tk.Tk()
    root.title("ユーザー登録")
    root.geometry("700x500")
    root.configure(bg="#f0f4f8")  # パステルカラー背景

    selected_user = tk.StringVar()
    countdown_label = None
    waiting = False

    def stop_waiting():
        nonlocal waiting
        waiting = False
        countdown_label.config(text="カードをスキャン")

    def on_user_selected(event):
        stop_waiting()
        selection = user_tree.selection()
        if not selection:
            return
        user_id = user_tree.item(selection[0])['values'][0]
        selected_user.set(user_id)
        start_countdown()

    def on_card_touched(serial_number):
        if not waiting:
            return
        user_id = selected_user.get()
        if not user_id:
            messagebox.showerror("エラー", "ユーザーが選択されていません。")
            return
        stop_waiting()
        update_user_serial(serial_number, user_id)
        send_user_event(config, user_id, serial_number)
        # ビープ音を鳴らす
        from util import beep
        beep()
        messagebox.showinfo("完了", f"シリアル番号 {serial_number} をユーザー {user_id} に登録しました。")

    def start_countdown():
        nonlocal waiting
        waiting = True
        countdown_label.config(text="カードスキャン待機中")

    frame = tk.Frame(root, bg="#ffffff", padx=10, pady=10)
    frame.pack(pady=10, fill="both", expand=True)

    tk.Label(frame, text="ユーザー一覧", font=("Helvetica", 14), bg="#ffffff").pack()

    columns = ("ID", "名前", "ログインID")
    user_tree = ttk.Treeview(frame, columns=columns, show="headings")
    for col in columns:
        user_tree.heading(col, text=col)
        user_tree.column(col, width=150)
    user_tree.pack(fill="both", expand=True)
    user_tree.bind("<<TreeviewSelect>>", on_user_selected)

    countdown_label = tk.Label(root, text="カードをスキャン", font=("Helvetica", 16), bg="#f0f4f8")
    countdown_label.pack(pady=10)

    users = get_users()
    for user in users:
        user_tree.insert("", tk.END, values=user)

    context = initialize_context()
    readers = list_readers(context)

    from util import monitor_readers
    reader_thread = threading.Thread(target=monitor_readers, args=(context, readers, on_card_touched), daemon=True)
    reader_thread.start()

    root.mainloop()

def signal_handler(sig, frame):
    print("\nプログラムを終了します...")
    from util import cleanup_buzzer
    cleanup_buzzer()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def main():
    global config
    config = load_config()
    initialize_db()
    
    # ブザーを初期化
    from util import setup_buzzer
    setup_buzzer()
    
    try:
        fetch_user_data(config)
        create_gui()
    except Exception as e:
        print(f"エラーが発生しました: {e}")
    finally:
        from util import cleanup_buzzer
        cleanup_buzzer()

if __name__ == "__main__":
    main()
