#!/usr/bin/env python3
"""
メインエントリーポイント。
"""

# 標準ライブラリ
import os
import sys
import signal
import time
import json
import subprocess
import threading
import traceback
from datetime import datetime

# サードパーティライブラリ
import tkinter as tk
from tkinter import ttk, messagebox
import RPi.GPIO as GPIO
import sdnotify
from smartcard.scard import SCardReleaseContext, SCardGetErrorMessage, SCARD_S_SUCCESS

# ローカルモジュール
from gui import create_gui
from card_reader import initialize_context, list_readers, monitor_readers
from db import initialize_db, fetch_user_data
from config import load_config
from logger import logger
from util.beep import setup_buzzer, cleanup_buzzer, set_volume  # ブザー関連の関数をインポート

# デバッグ情報の出力
logger.debug(f"Python version: {sys.version}")
logger.debug(f"Python path: {sys.path}")
logger.debug(f"Current working directory: {os.getcwd()}")
logger.debug(f"Environment variables: {os.environ}")

# Xサーバーが利用可能かチェック
def check_x_server():
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
notifier = sdnotify.SystemdNotifier()

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

        # ユーザーデータ取得（最大3回リトライ）
        retry_count = 0
        max_retries = 3
        user_data = None
        
        while retry_count < max_retries:
            try:
                user_data = fetch_user_data(config)
                if user_data:
                    logger.info(f"ユーザーデータを取得しました（{len(user_data)}件）")
                    break
                else:
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.warning(f"ユーザーデータの取得に失敗しました。{retry_count}回目のリトライを実行します...")
                        time.sleep(2)  # 2秒待機してリトライ
                    else:
                        logger.error("ユーザーデータの取得に失敗しました。最大リトライ回数を超えました。")
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    logger.warning(f"ユーザーデータの取得中にエラーが発生: {e}。{retry_count}回目のリトライを実行します...")
                    time.sleep(2)
                else:
                    logger.error(f"ユーザーデータの取得中にエラーが発生: {e}。最大リトライ回数を超えました。")

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

            # GUI生成
            state_var, time_label, info_label = create_gui(root, config)

            # スレッド停止用イベント
            stop_event = threading.Event()

            # リーダー監視スレッド開始
            monitor_thread = threading.Thread(
                target=monitor_readers,
                args=(context, readers, state_var, root, info_label, config, stop_event),
                daemon=True
            )
            monitor_thread.start()

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
                notifier.notify("STOPPING=1")
                root.destroy()
                sys.exit(0)

            root.protocol("WM_DELETE_WINDOW", on_closing)

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
                hresult = SCardReleaseContext(context)
                if hresult != SCARD_S_SUCCESS:
                    logger.error(f"コンテキストの解放に失敗: {SCardGetErrorMessage(hresult)}")
                else:
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