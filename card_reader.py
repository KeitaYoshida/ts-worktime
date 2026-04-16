import time
import requests
from datetime import datetime
import os
from pathlib import Path

import smartcard.util
from smartcard.scard import (
    SCardEstablishContext,
    SCardListReaders,
    SCardGetErrorMessage,
    SCardGetStatusChange,
    SCardConnect,
    SCardDisconnect,
    SCARD_SCOPE_USER,
    SCARD_STATE_UNAWARE,
    SCARD_STATE_PRESENT,
    SCARD_SHARE_SHARED,
    SCARD_PROTOCOL_T0,
    SCARD_PROTOCOL_T1,
    SCARD_UNPOWER_CARD,
    SCardTransmit,
    SCARD_PCI_T1,
    SCARD_S_SUCCESS,
)

from db import get_user_by_serial, save_to_db, update_attendance
from util.beep import beep, play_error_melody, play_success_melody
from logger import logger

def initialize_context():
    """PC/SCコンテキストを確立する"""
    try:
        hresult, context = SCardEstablishContext(SCARD_SCOPE_USER)
        if hresult != SCARD_S_SUCCESS:
            error_msg = f"コンテキストの確立に失敗: {SCardGetErrorMessage(hresult)}"
            logger.error(error_msg)
            raise Exception(error_msg)
        logger.info("PC/SCコンテキストが確立されました")
        return context
    except Exception as e:
        logger.error(f"コンテキスト初期化エラー: {e}")
        raise

def list_readers(context):
    """スマートカードリーダーのリストを取得する"""
    try:
        hresult, readers = SCardListReaders(context, [])
        if hresult != SCARD_S_SUCCESS:
            error_msg = f"リーダーの取得に失敗: {SCardGetErrorMessage(hresult)}"
            logger.error(error_msg)
            raise Exception(error_msg)
        if not readers:
            error_msg = "スマートカードリーダーが見つかりません"
            logger.error(error_msg)
            raise Exception(error_msg)
        logger.info(f"検出されたPC/SCリーダー: {readers}")
        return readers
    except Exception as e:
        logger.error(f"リーダー一覧取得エラー: {e}")
        raise

def get_card_serial_number(card):
    """カードのシリアル番号を取得して10進数に変換"""
    APDU_GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]

    try:
        hresult, response = SCardTransmit(card, SCARD_PCI_T1, APDU_GET_UID)
        if hresult != SCARD_S_SUCCESS:
            logger.error(f"シリアル番号の取得に失敗: {SCardGetErrorMessage(hresult)}")
            return None

        if not response or len(response) < 2:
            logger.error("シリアル番号の応答が無効です")
            return None

        hex_serial = smartcard.util.toHexString(response[:-2]).replace(" ", "")
        if not hex_serial:
            logger.error("無効なシリアル番号の応答")
            return None

        decimal_serial = int(hex_serial, 16)
        logger.debug(f"シリアル番号 (10進数): {decimal_serial}")
        return decimal_serial
    except ValueError as e:
        logger.error(f"シリアル番号の変換に失敗: {e}")
        return None
    except Exception as e:
        logger.error(f"シリアル番号取得中の予期せぬエラー: {e}")
        return None

def handle_card_data(serial_number, state_var, config, callback_success, callback_error):
    """カードデータの処理"""
    try:
        current_state = state_var.get()
        logger.info(f"カード処理開始 - シリアル: {serial_number}, 状態: {current_state}")
        
        user_info = get_user_by_serial(serial_number)
        if not user_info:
            logger.warning(f"未登録のシリアル番号: {serial_number}")
            play_error_melody()
            callback_error("シリアル番号が未登録です。ユーザー設定から登録してください", current_state)
            return

        # DBに保存
        save_record = save_to_db(serial_number, current_state, user_info)
        logger.debug(f"DB保存完了 - ID: {save_record['id']}")
        
        # API送信
        try:
            api_url = config.get("set_timestamp_api")
            payload = {
                "marge_id": save_record['id'],
                "serial_no": serial_number,
                "state": current_state,
                "user_id": user_info.get("res_user_id"),
                "user_name": user_info.get("name"),
                "timestamp": datetime.now().isoformat()
            }
            logger.debug(f"API送信開始: {api_url}")
            response = requests.post(api_url, json=payload, timeout=5)  # タイムアウト追加
            
            if response.status_code in [200, 201]:
                update_attendance(save_record['id'], 'marge', 1)
                logger.info(f"処理成功 - ユーザー: {user_info['name']}")
                play_success_melody()
                callback_success(user_info["name"], current_state)
            else:
                error_msg = f"API送信失敗: {response.status_code}"
                logger.error(error_msg)
                play_error_melody()
                callback_error(error_msg, current_state)
        except requests.Timeout:
            logger.error("API送信がタイムアウトしました")
            play_error_melody()
            callback_error("サーバー接続がタイムアウトしました", current_state)
        except requests.RequestException as e:
            logger.error(f"API送信エラー: {e}")
            play_error_melody()
            callback_error(f"API送信中エラー: {e}", current_state)
    except Exception as e:
        logger.error(f"カード処理中の予期せぬエラー: {e}")
        play_error_melody()
        callback_error("システムエラーが発生しました", current_state)

def monitor_readers(context, readers, state_var, root, info_label, config, stop_event):
    """カードリーダーの監視"""
    from gui import update_user_label

    def on_success(name, state):
        # 即時フィードバック（0.1秒後にリセット）
        info_label.after(100, lambda: update_user_label(
            info_label,
            f"{name} さんの記録成功",
            state,
            "#D8E3FF",
            text_color="#1E3A8A",
            font_weight="bold",
            change_bg=False
        ))
    
    def on_error(message, state):
        # エラー表示は1秒間表示
        info_label.after(1000, lambda: update_user_label(
            info_label,
            message,
            state,
            "#FECACA",
            text_color="#C2185B",
            font_weight="bold",
            change_bg=False
        ))

    last_card_time = 0  # 最後のカード読み取り時刻
    
    try:
        while not stop_event.is_set():
            try:
                for reader in readers:
                    # カード状態の取得（タイムアウト100ms）
                    hresult, card_status = SCardGetStatusChange(context, 100, [(reader, SCARD_STATE_UNAWARE)])
                    if hresult != SCARD_S_SUCCESS:
                        continue

                    reader_state = card_status[0][1]
                    current_time = time.time()

                    if reader_state & SCARD_STATE_PRESENT:
                        # 最後の読み取りから1秒以上経過している場合のみ処理
                        if current_time - last_card_time >= 1:
                            try:
                                hresult, card, protocol = SCardConnect(
                                    context, reader, SCARD_SHARE_SHARED,
                                    SCARD_PROTOCOL_T0 | SCARD_PROTOCOL_T1
                                )
                                if hresult != SCARD_S_SUCCESS:
                                    continue

                                try:
                                    serial_number = get_card_serial_number(card)
                                    if serial_number is not None:
                                        beep()
                                        handle_card_data(serial_number, state_var, config, on_success, on_error)
                                        last_card_time = current_time
                                finally:
                                    SCardDisconnect(card, SCARD_UNPOWER_CARD)
                            except Exception as e:
                                logger.error(f"カード接続エラー: {e}")
                                on_error("カードの読み取りに失敗しました", state_var.get())

                time.sleep(0.1)  # ポーリング間隔を0.1秒に短縮
            except Exception as e:
                logger.error(f"リーダー監視中のエラー: {e}")
                time.sleep(1)  # エラー時は1秒待機
                
    except Exception as e:
        logger.critical(f"致命的なエラーが発生: {e}")
        if root:
            logger.info("アプリケーションを再起動します...")
            root.after(0, lambda: (
                root.quit(),
                root.destroy(),
                os.execv(sys.executable, ['python'] + sys.argv)
            ))