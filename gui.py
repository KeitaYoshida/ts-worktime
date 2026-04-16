import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import csv
import zipfile
import sqlite3
import requests
import json

from config import save_config
from db import DB_FILE


import tkinter as tk
from tkinter import ttk
from tkinter import font

# グローバル変数（自動切替の一時停止状態）
auto_switch_suspended = False
touch_notification_active = False  # カードタッチ通知中かどうか

def update_time(label, state_var, info_label, status_colors):
    """
    現在時刻を表示するとともに、auto_switch_suspended および touch_notification_active が False の場合、
    11時前なら「出勤」、11時以降なら「退勤」に自動切り替え、info_label の表示も更新する。
    """
    current_time = datetime.now()
    formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
    spaced_time = " ".join(formatted_time)
    label.config(text=spaced_time)
    
    global auto_switch_suspended, touch_notification_active
    if not auto_switch_suspended and not touch_notification_active:
        new_state = "出勤" if current_time.hour < 11 else "退勤"
        state_var.set(new_state)
        info_label.config(
            text=f"現在のステータス: {new_state}\nカード受付待機中...",
            bg=status_colors[new_state],
            fg="#1E3A8A"
        )
    
    label.after(1000, update_time, label, state_var, info_label, status_colors)


def create_gui(root, config):
    """
    メインのGUIを作成して返す。
    ・ウィンドウサイズは WVGA (800x480) に固定し、全画面で起動
    ・自動切替機能：11時前は「出勤」、11時以降は「退勤」
    ・ステータスボタン押下時は、30秒間自動切替を停止
    """
    # カスタムフォント設定
    noto_sans_font = font.Font(family="Noto Sans", size=16)
    status_font = font.Font(family="Noto Sans", size=20)  # ステータス表示用の専用フォント
    digital_font = font.Font(family="Digital-7", size=32)

    style = ttk.Style()
    style.configure("Wide.TButton", font=noto_sans_font, padding=(10, 10))

    background_color = "#FAFAFA"
    root.configure(bg=background_color)

    root.title("出退勤管理")
    root.geometry("800x480")
    root.resizable(False, False)
    root.after(500, lambda: root.attributes("-fullscreen", True))

    status_colors = {
        "出勤": "#D8E3FF",
        "退勤": "#FEE2E2",
        "外出": "#D1FAE5",
        "戻り": "#E9D5FF",
    }
    button_hover_colors = {
        "出勤": "#BFDBFE",
        "退勤": "#FECACA",
        "外出": "#A7F3D0",
        "戻り": "#D8B4FE",
    }

    main_frame = tk.Frame(root, bg=background_color, padx=10, pady=0)
    main_frame.pack(expand=True, fill=tk.BOTH)

    settings_button = tk.Label(
        main_frame,
        text="⚙ 設定",
        font=noto_sans_font,
        cursor="hand2",
        bg=background_color,
        fg="#1E3A8A"
    )
    settings_button.pack(anchor=tk.NE, pady=(0, 2))
    settings_button.bind("<Button-1>", lambda e: open_settings_window(root, config))

    time_frame = tk.Frame(main_frame, bg="#F5F5F5")
    time_frame.pack(fill=tk.X, pady=(0, 8))  # 時間表示の下の空白を増やす
    time_label = tk.Label(
        time_frame,
        text="2 0 2 5 - 0 1 - 2 9   1 6 : 5 9 : 5 5",
        font=digital_font,
        fg="#1E3A8A",
        bg="#F5F5F5"
    )
    time_label.pack(pady=2)
    
    state_var = tk.StringVar(value="出勤")

    info_label = tk.Label(
        main_frame,
        text="現在のステータス: 出勤\nカード受付待機中...",
        font=status_font,  # 専用フォントを使用
        fg="#1E3A8A",
        bg=status_colors["出勤"],
        anchor="center",
        height=3,
        wraplength=600
    )
    info_label.pack(fill=tk.X, pady=(0, 8), padx=10)  # ステータス表示の下の空白を増やす

    def suspend_auto_switch():
        global auto_switch_suspended
        auto_switch_suspended = True
        root.after(30000, reset_auto_switch)

    def reset_auto_switch():
        global auto_switch_suspended
        auto_switch_suspended = False

    button_frame = tk.Frame(main_frame, bg=background_color)
    button_frame.pack(expand=True, pady=(0, 0))

    filtered_states = ["出勤", "退勤"]  # 表示対象のステータスを明示的に指定

    for i, state in enumerate(filtered_states):
        button = tk.Button(
            button_frame,
            text=state,
            font=font.Font(family="Noto Sans", size=18),
            width=12,
            height=2,
            bg=status_colors[state],
            fg="#1E3A8A",
            activebackground=button_hover_colors[state],
            activeforeground="#1E3A8A",
            relief="raised",
            command=lambda s=state: [
                state_var.set(s),
                update_status_label(s, info_label, status_colors[s]),
                suspend_auto_switch()
            ]
        )
        button.grid(row=i // 2, column=i % 2, padx=25, pady=10)

    # update_time を state_var, info_label, status_colors を渡して開始
    update_time(time_label, state_var, info_label, status_colors)

    return state_var, time_label, info_label


def update_status_label(state, info_label, bg_color=None):
    """
    ステータス変更時にラベルの背景色とテキストを更新
    """
    if bg_color is None:
        bg_color = info_label["bg"]  # 現在の背景色を取得

    info_label.config(
        text=f"現在のステータス: {state}\nカード受付待機中...",
        bg=bg_color,
        fg="#1E3A8A"
    )


def update_user_label(info_label, info, state, status_color, text_color="#1E3A8A", font_weight="normal", change_bg=True):
    """
    ユーザー情報や状態をラベルに通知表示する。
    ・change_bg が True なら背景色も status_color に設定、False なら現状の背景色を維持する。
    ・通知表示後、1500ms 後にデフォルトの「カード受付待機中...」表示に戻す。
    """
    global touch_notification_active
    touch_notification_active = True  # 通知中フラグをオン

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = f"現在のステータス: {state}\n{info}\n[{timestamp}]" if info else f"現在のステータス: {state}\nカード受付待機中..."
    
    current_bg = info_label.cget("bg")
    bg_to_use = status_color if change_bg else current_bg

    # info_label の現在のフォントから新たなフォントオブジェクトを生成
    custom_font = font.Font(font=info_label.cget("font"))
    custom_font.configure(weight=font_weight)
    
    info_label.config(text=text, bg=bg_to_use, fg=text_color, font=custom_font)
    
    # 1500ms 後にデフォルトの状態に戻す
    def reset_label():
        global touch_notification_active
        default_fg = "#1E3A8A"
        default_weight = "normal"
        # フォントサイズを20に固定
        default_font = font.Font(family="Noto Sans", size=20, weight=default_weight)
        # 背景色は change_bg により status_color か現状の背景色
        reset_bg = status_color if change_bg else current_bg
        info_label.config(
            text=f"現在のステータス: {state}\nカード受付待機中...",
            bg=reset_bg,
            fg=default_fg,
            font=default_font
        )
        touch_notification_active = False  # 通知終了
    info_label.after(2000, reset_label)


def on_state_button_click(state, state_var, state_label):
    """
    ステートボタンをクリックしたときに呼ばれる
    """
    state_var.set(state)
    state_label.config(text=state)


# def update_user_label(label, info, state):
#     """
#     ユーザー情報や状態をラベルに表示
#     """
#     timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     text = f"{info}\n[{state}] {timestamp}" if info else ""
#     label.config(text=text)


# def update_time(label):
#     """
#     現在時刻を更新し続ける（文字間にスペースを追加）
#     """
#     # 現在時刻を取得
#     current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

#     # 各文字間にスペースを追加
#     spaced_time = " ".join(current_time)

#     # ラベルを更新
#     label.config(text=spaced_time)

#     # 1秒ごとに再実行
#     label.after(1000, update_time, label)


def open_settings_window(root, config):
    """
    設定画面を表示
    """
    settings_window = tk.Toplevel(root)
    settings_window.title("設定")

    # ラベルとエントリーの作成
    labels = [
        ("サーバーヘルスチェックAPI:", "server_helth_api"),
        ("ユーザーリストAPI:", "user_list_api"),
        ("タイムスタンプ送信API:", "set_timestamp_api"),
        ("マージAPI:", "marge_api"),
        ("ユーザーデータファイル:", "user_data_file"),
        ("ユーザーシリアル登録API:", "set_user_serial"),
        ("サーバーURL:", "server_url"),
        ("ユーザーID:", "user_id"),
    ]

    entries = {}

    for i, (label_text, key) in enumerate(labels):
        tk.Label(settings_window, text=label_text).grid(row=i, column=0, sticky=tk.W, padx=10, pady=5)
        entry = tk.Entry(settings_window, width=40)
        entry.grid(row=i, column=1, padx=10, pady=5)
        entry.insert(0, config.get(key, ""))  # デフォルトで値を取得
        entries[key] = entry

    # 自動同期オプション
    auto_sync_var = tk.BooleanVar(value=config.get("auto_sync", False))
    tk.Checkbutton(settings_window, text="自動同期を有効にする", variable=auto_sync_var).grid(
        row=len(labels), column=0, columnspan=2, pady=5
    )

    def save_settings():
        """
        設定を保存
        """
        for key, entry in entries.items():
            config[key] = entry.get()

        config["auto_sync"] = auto_sync_var.get()

        # 設定を保存（仮の保存処理）
        with open("config.json", "w") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

        settings_window.destroy()

    def merge_records():
        """
        未連携データをマージAPIに送信
        """
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, serial_number, timestamp, state, back_user_id, user_name, login_id
                FROM attendance
                WHERE marge IS NULL OR marge = 0
            """)
            records = cursor.fetchall()

            if not records:
                messagebox.showinfo("マージ", "未連携のデータはありません。")
                return

            payload = []
            for record in records:
                payload.append({
                    "marge_id": record[0],
                    "serial_no": record[1],
                    "timestamp": record[2],
                    "state": record[3],
                    "user_id": record[4],
                    "user_name": record[5],
                    "login_id": record[6],
                })

            response = requests.post(config["marge_api"], json=payload)
            if response.status_code == 200:
                # 成功 -> margeを1に更新
                record_ids = [rec[0] for rec in records]
                placeholders = ",".join("?" for _ in record_ids)
                cursor.execute(f"UPDATE attendance SET marge = 1 WHERE id IN ({placeholders})", record_ids)
                conn.commit()
                messagebox.showinfo("マージ", "データの連携に成功しました。")
            else:
                messagebox.showerror("エラー", f"データ連携に失敗: {response.status_code}")

        except Exception as e:
            messagebox.showerror("エラー", f"データ連携中にエラーが発生しました。\n{e}")
        finally:
            conn.close()

    def export_to_csv():
        """
        未連携データをCSV出力
        """
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, serial_number, timestamp, state, back_user_id, user_name, login_id
                FROM attendance
                WHERE marge IS NULL OR marge = 0
            """)
            records = cursor.fetchall()

            if not records:
                messagebox.showinfo("CSV出力", "未連携のデータはありません。")
                return

            csv_file = f"attendance_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            zip_file = f"attendance_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

            # CSV書き込み
            with open(csv_file, "w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(["ID", "Serial Number", "Timestamp", "State", "Back User ID", "User Name", "Login ID"])
                writer.writerows(records)

            # ZIP圧縮
            with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(csv_file, arcname=csv_file)

            # marge を 1 に更新
            record_ids = [rec[0] for rec in records]
            placeholders = ",".join("?" for _ in record_ids)
            cursor.execute(f"UPDATE attendance SET marge = 1 WHERE id IN ({placeholders})", record_ids)
            conn.commit()

            messagebox.showinfo("CSV出力", f"CSV出力が完了しました。\nZIPファイル: {zip_file}")
            print(f"ZIPファイルが生成されました: {zip_file}")

        except Exception as e:
            messagebox.showerror("エラー", f"CSV出力中にエラーが発生しました。\n{e}")
        finally:
            conn.close()

    # 設定画面のボタン
    button_frame = tk.Frame(settings_window)
    button_frame.grid(row=len(labels) + 1, columnspan=2, pady=10)

    tk.Button(button_frame, text="保存", command=save_settings).pack(side=tk.LEFT, padx=5)
    tk.Button(button_frame, text="マージ", command=merge_records).pack(side=tk.LEFT, padx=5)
    tk.Button(button_frame, text="CSV出力", command=export_to_csv).pack(side=tk.LEFT, padx=5)
