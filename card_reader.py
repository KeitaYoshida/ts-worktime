import time
import os
import sys

try:
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
        SCardReleaseContext,
    )
    SMARTCARD_AVAILABLE = True
except Exception:
    smartcard = None
    SCardEstablishContext = None
    SCardListReaders = None
    SCardGetErrorMessage = None
    SCardGetStatusChange = None
    SCardConnect = None
    SCardDisconnect = None
    SCARD_SCOPE_USER = None
    SCARD_STATE_UNAWARE = None
    SCARD_STATE_PRESENT = None
    SCARD_SHARE_SHARED = None
    SCARD_PROTOCOL_T0 = None
    SCARD_PROTOCOL_T1 = None
    SCARD_UNPOWER_CARD = None
    SCardTransmit = None
    SCARD_PCI_T1 = None
    SCARD_S_SUCCESS = None
    SCardReleaseContext = None
    SMARTCARD_AVAILABLE = False

from util.beep import beep
from logger import logger

def initialize_context():
    """PC/SCコンテキストを確立する"""
    if not SMARTCARD_AVAILABLE:
        logger.warning("smartcard ライブラリが未導入のため、カードリーダー機能を無効化します")
        return None
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
    if not SMARTCARD_AVAILABLE or context is None:
        return []
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
    if not SMARTCARD_AVAILABLE:
        return None
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

def monitor_readers(context, readers, on_card_detected, on_error, stop_event):
    """カードリーダーの監視"""
    if not SMARTCARD_AVAILABLE or context is None or not readers:
        logger.info("カードリーダー監視は無効です")
        while not stop_event.wait(1):
            pass
        return

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
                                        on_card_detected(serial_number)
                                        last_card_time = current_time
                                finally:
                                    SCardDisconnect(card, SCARD_UNPOWER_CARD)
                            except Exception as e:
                                logger.error(f"カード接続エラー: {e}")
                                on_error("カードの読み取りに失敗しました")

                time.sleep(0.1)  # ポーリング間隔を0.1秒に短縮
            except Exception as e:
                logger.error(f"リーダー監視中のエラー: {e}")
                time.sleep(1)  # エラー時は1秒待機
                
    except Exception as e:
        logger.critical(f"致命的なエラーが発生: {e}")
        logger.info("アプリケーションを再起動します...")
        os.execv(sys.executable, ['python'] + sys.argv)


def release_context(context):
    if not SMARTCARD_AVAILABLE or context is None or SCardReleaseContext is None:
        return
    hresult = SCardReleaseContext(context)
    if hresult != SCARD_S_SUCCESS:
        raise RuntimeError(f"コンテキストの解放に失敗: {SCardGetErrorMessage(hresult)}")
