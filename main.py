#!/usr/bin/env python3
"""
メインエントリーポイント。
"""

# 標準ライブラリ
import os
import sys
import signal
import time
import subprocess
import threading
import traceback
from datetime import datetime

# サードパーティライブラリ
import requests
import tkinter as tk
from tkinter import ttk, messagebox

# ローカルモジュール
from gui import create_gui, open_registration_window, update_user_label
from card_reader import (
    SMARTCARD_AVAILABLE,
    initialize_context,
    list_readers,
    monitor_readers,
    release_context,
)
from db import initialize_db, get_user_by_serial, save_to_db, update_attendance
from config import load_config
from logger import logger
from platform_compat import IS_LINUX, IS_MAC, create_notifier
from registration import RegistrationSession
from user_service import register_user_card, sync_user_data
from util.beep import (
    setup_buzzer,
    cleanup_buzzer,
    set_volume,
    play_error_melody,
    play_success_melody,
)

# デバッグ情報の出力
logger.debug(f"Python version: {sys.version}")
logger.debug(f"Python path: {sys.path}")
logger.debug(f"Current working directory: {os.getcwd()}")
logger.debug(f"Environment variables: {os.environ}")

# Xサーバーが利用可能かチェック
def check_x_server():
    if not IS_LINUX:
        return True
    try:
        subprocess.run(['xset', 'q'], capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        logger.error("Xサーバーが利用できません")
        return False
    except Exception as e:
        logger.error(f"Xサーバーチェックエラー: {e}")
        return False

# systemd通知用のオブジェクト
notifier = create_notifier()
root = None

def restart_application():
    """アプリケーションを再起動"""
    logger.info("アプリケーションを再起動します...")
    try:
        # systemdに再起動を通知
        notifier.notify("RELOADING=1")
        os.execv(sys.executable, ['python3'] + sys.argv)
    except Exception as e:
        logger.error(f"再起動に失敗しました: {e}")
        sys.exit(1)

def signal_handler(sig, frame):
    """シグナルハンドラ"""
    global root
    logger.info("終了シグナルを受信しました...")
    if root is not None:
        try:
            root.attributes("-fullscreen", False)
            if IS_LINUX:
                root.overrideredirect(False)
        except Exception as e:
            logger.error(f"全画面解除エラー: {e}")
        root.quit()
        root.destroy()
    # ブザーのクリーンアップ
    cleanup_buzzer()
    # systemdに停止を通知
    notifier.notify("STOPPING=1")
    sys.exit(0)

# シグナルハンドラの登録
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def check_single_instance():
    """
    重複起動をチェック
    """
    try:
        pid_file = "/tmp/worktime.pid"
        
        # 既存のPIDファイルをチェック
        if os.path.exists(pid_file):
            with open(pid_file, 'r') as f:
                old_pid = int(f.read().strip())
            try:
                # プロセスが存在するかチェック
                os.kill(old_pid, 0)
                logger.warning(f"既に別のインスタンスが実行中です (PID: {old_pid})")
                return False
            except OSError:
                # プロセスが存在しない場合はPIDファイルを削除
                os.remove(pid_file)
        
        # 新しいPIDを書き込み
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
        return True
        
    except Exception as e:
        logger.error(f"プロセスチェックエラー: {e}")
        return True  # エラー時は実行を許可

def check_display():
    """
    DISPLAY環境変数が正しく設定されているか確認
    """
    if IS_MAC:
        return True

    display = os.environ.get('DISPLAY')
    if not display:
        logger.error("DISPLAY環境変数が設定されていません")
        return False
    
    xauth = os.environ.get('XAUTHORITY')
    if not xauth:
        logger.warning("XAUTHORITY環境変数が設定されていません")
    
    return True

def main():
    """メイン処理"""
    try:
        if not check_single_instance():
            sys.exit(1)

        logger.info("アプリケーションを起動します...")
        
        # DISPLAY環境変数のチェック
        if not check_display():
            logger.error("GUI環境が正しく設定されていません")
            sys.exit(1)
        
        # Xサーバーチェック
        if not check_x_server():
            sys.exit(1)
        
        # systemdに起動中を通知
        notifier.notify("STATUS=Initializing...")
        
        # 設定ロード
        config = load_config()
        logger.debug("設定をロードしました")
        
        # ブザーの初期化と音量設定
        setup_buzzer()
        set_volume(config.get('buzzer_volume', 70))  # デフォルト音量70%
        logger.debug(f"ブザーを初期化しました（音量: {config.get('buzzer_volume', 70)}%）")

        # DB初期化
        initialize_db()
        logger.debug("データベースを初期化しました")

        # カードリーダー初期化
        context = initialize_context()
        logger.debug("カードリーダーコンテキストを初期化しました")

        def sync_users_with_retry():
            retry_count = 0
            max_retries = 3

            while retry_count < max_retries:
                try:
                    user_data = sync_user_data(config)
                    if user_data:
                        logger.info(f"ユーザーデータを取得しました（{len(user_data)}件）")
                        return True
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.warning(
                            "ユーザーデータの取得に失敗しました。%s回目のリトライを実行します...",
                            retry_count,
                        )
                        time.sleep(2)
                except Exception as e:
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.warning(
                            "ユーザーデータの取得中にエラーが発生: %s。%s回目のリトライを実行します...",
                            e,
                            retry_count,
                        )
                        time.sleep(2)

            logger.error("ユーザーデータの取得に失敗しました。最大リトライ回数を超えました。")
            return False

        sync_users_with_retry()

        try:
            # カードリーダー一覧を取得
            readers = list_readers(context)
            logger.info("カードリーダーの準備が完了しました")

            # systemdに準備完了を通知
            notifier.notify("READY=1")
            notifier.notify("STATUS=Running")

            # Tkinterウィンドウ作成
            global root
            root = tk.Tk()
            root.title("出退勤管理")

            registration_session = RegistrationSession()

            def show_registration_mode(user_name):
                info_label.config(
                    text=f"カード登録モード\n{user_name} さんのカードを待機中...",
                    fg="#1E3A8A",
                    bg="#FEF3C7",
                )

            def clear_registration_mode():
                current_state = state_var.get()
                current_bg = "#4F7DFF" if current_state == "出勤" else "#FF8A7A"
                info_label.config(
                    text=f"現在のステータス: {current_state}\nカード受付待機中...",
                    fg="#FFFFFF",
                    bg=current_bg,
                )

            # GUI生成
            state_var, time_label, info_label = create_gui(
                root,
                config,
                lambda: open_registration_window(
                    root,
                    registration_session,
                    sync_users_with_retry,
                    show_registration_mode,
                    clear_registration_mode,
                ),
                lambda: root.event_generate("<<RequestClose>>", when="tail"),
            )

            # スレッド停止用イベント
            stop_event = threading.Event()

            def show_attendance_success(name, state):
                info_label.after(
                    100,
                    lambda: update_user_label(
                        info_label,
                        f"{name} さんの記録成功",
                        state,
                        "#D8E3FF",
                        text_color="#1E3A8A",
                        font_weight="bold",
                        change_bg=False,
                    ),
                )

            def show_attendance_error(message, state):
                info_label.after(
                    1000,
                    lambda: update_user_label(
                        info_label,
                        message,
                        state,
                        "#FECACA",
                        text_color="#C2185B",
                        font_weight="bold",
                        change_bg=False,
                    ),
                )

            def handle_attendance_card(serial_number):
                current_state = state_var.get()
                logger.info(
                    "カード処理開始 - シリアル: %s, 状態: %s",
                    serial_number,
                    current_state,
                )

                user_info = get_user_by_serial(serial_number)
                if not user_info:
                    logger.warning("未登録のシリアル番号: %s", serial_number)
                    play_error_melody()
                    show_attendance_error(
                        "シリアル番号が未登録です。カード登録から設定してください",
                        current_state,
                    )
                    return

                save_record = save_to_db(serial_number, current_state, user_info)

                try:
                    api_url = config.get("set_timestamp_api")
                    payload = {
                        "marge_id": save_record["id"],
                        "serial_no": serial_number,
                        "state": current_state,
                        "user_id": user_info.get("res_user_id"),
                        "user_name": user_info.get("name"),
                        "timestamp": datetime.now().isoformat(),
                    }
                    response = requests.post(api_url, json=payload, timeout=5)

                    if response.status_code in [200, 201]:
                        update_attendance(save_record["id"], "marge", 1)
                        logger.info("処理成功 - ユーザー: %s", user_info["name"])
                        play_success_melody()
                        show_attendance_success(user_info["name"], current_state)
                        return

                    error_msg = f"API送信失敗: {response.status_code}"
                    logger.error(error_msg)
                    play_error_melody()
                    show_attendance_error(error_msg, current_state)
                except requests.Timeout:
                    logger.error("API送信がタイムアウトしました")
                    play_error_melody()
                    show_attendance_error("サーバー接続がタイムアウトしました", current_state)
                except requests.RequestException as e:
                    logger.error("API送信エラー: %s", e)
                    play_error_melody()
                    show_attendance_error(f"API送信中エラー: {e}", current_state)

            def handle_registration_card(serial_number):
                selected_user = registration_session.get_selected_user()
                if not selected_user:
                    play_error_melody()
                    messagebox.showwarning("カード登録", "先に登録するユーザーを選択してください。")
                    return

                success, error_message = register_user_card(
                    config,
                    selected_user["id"],
                    serial_number,
                )

                if success:
                    registration_session.clear()
                    clear_registration_mode()
                    close_registration_view = getattr(root, "_close_registration_view", None)
                    if close_registration_view is not None:
                        close_registration_view()
                    play_success_melody()
                    current_state = state_var.get()
                    info_label.after(
                        100,
                        lambda: update_user_label(
                            info_label,
                            f"{selected_user['name']} さんにカードを登録しました",
                            current_state,
                            "#D8E3FF",
                            text_color="#1E3A8A",
                            font_weight="bold",
                            change_bg=False,
                        ),
                    )
                    messagebox.showinfo(
                        "カード登録完了",
                        f"{selected_user['name']} さんへカードを登録しました。",
                    )
                    return

                play_error_melody()
                current_state = state_var.get()
                show_attendance_error(error_message, current_state)
                messagebox.showerror("カード登録エラー", error_message)

            def handle_detected_card(serial_number):
                if getattr(root, "_registration_mode_visible", False):
                    root.after(0, lambda: handle_registration_card(serial_number))
                else:
                    handle_attendance_card(serial_number)

            def handle_reader_error(message):
                current_state = state_var.get()
                show_attendance_error(message, current_state)

            if not SMARTCARD_AVAILABLE:
                info_label.config(
                    text="開発モード\nカードリーダー機能は無効です",
                    fg="#1E3A8A",
                    bg="#E2E8F0",
                )

            # リーダー監視スレッド開始
            monitor_thread = threading.Thread(
                target=monitor_readers,
                args=(context, readers, handle_detected_card, handle_reader_error, stop_event),
                daemon=True,
            )
            monitor_thread.start()

            def user_sync_worker():
                while not stop_event.wait(300):
                    try:
                        sync_user_data(config)
                    except Exception as exc:
                        logger.error("定期ユーザー同期エラー: %s", exc)

            sync_thread = threading.Thread(target=user_sync_worker, daemon=True)
            sync_thread.start()

            # Watchdog通知用スレッド
            def watchdog_notifier():
                while not stop_event.is_set():
                    notifier.notify("WATCHDOG=1")
                    time.sleep(30)  # 30秒ごとに生存通知

            watchdog_thread = threading.Thread(target=watchdog_notifier, daemon=True)
            watchdog_thread.start()

            # ウィンドウを閉じる際の処理
            def on_closing():
                logger.info("アプリケーションを終了します...")
                stop_event.set()
                registration_session.clear()
                clear_registration_mode()
                notifier.notify("STOPPING=1")
                if IS_LINUX:
                    try:
                        root.overrideredirect(False)
                        root.attributes("-fullscreen", False)
                    except tk.TclError:
                        pass
                root.destroy()
                sys.exit(0)

            root.protocol("WM_DELETE_WINDOW", on_closing)
            root.bind("<<RequestClose>>", lambda _event: on_closing())

            # エラーハンドラ
            def handle_exception(exc_type, exc_value, exc_traceback):
                if issubclass(exc_type, KeyboardInterrupt):
                    sys.__excepthook__(exc_type, exc_value, exc_traceback)
                    return
                
                logger.critical("予期せぬエラーが発生しました:", exc_info=(exc_type, exc_value, exc_traceback))
                notifier.notify("STATUS=Error occurred, restarting...")
                
                # GUIスレッドでない場合は、GUIスレッドで再起動を実行
                if threading.current_thread() is threading.main_thread():
                    root.after(0, restart_application)
                else:
                    logger.error("バックグラウンドスレッドでエラーが発生しました")

            # グローバルな例外ハンドラを設定
            sys.excepthook = handle_exception

            # メインループ開始
            root.mainloop()

        finally:
            # PC/SCコンテキストを解放
            try:
                release_context(context)
                logger.info("コンテキストを解放しました")
            except Exception as e:
                logger.error(f"コンテキスト解放中にエラー: {e}")

    except Exception as e:
        logger.critical(f"アプリケーション起動中に致命的なエラーが発生: {e}")
        logger.critical(traceback.format_exc())
        notifier.notify("STATUS=Fatal error occurred, restarting...")
        time.sleep(3)  # エラーメッセージを表示するための待機
        restart_application()

if __name__ == "__main__":
    main()
