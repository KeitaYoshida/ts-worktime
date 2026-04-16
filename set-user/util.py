import os
from smartcard.scard import *
import smartcard.util
import time
import RPi.GPIO as GPIO

# GPIOブザー用の設定
BUZZER_PIN = 18

def setup_buzzer():
    """ブザーの初期化"""
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUZZER_PIN, GPIO.OUT)
    GPIO.setwarnings(False)
    global pwm
    pwm = GPIO.PWM(BUZZER_PIN, 1000)  # PWM初期化
    pwm.start(0)

def cleanup_buzzer():
    """ブザーのクリーンアップ"""
    try:
        pwm.stop()
        GPIO.cleanup(BUZZER_PIN)
    except:
        pass

def beep():
    """ブザーを鳴らす（GPIO使用）"""
    try:
        pwm.ChangeDutyCycle(50)  # 50%のデューティ比で音を鳴らす
        time.sleep(0.2)
        pwm.ChangeDutyCycle(0)
    except Exception as e:
        print(f"ブザーエラー: {e}")

def monitor_readers(context, readers, on_card_touched):
    """リーダーを監視し、カードが検出された場合にシリアル番号を取得"""
    try:
        while True:
            for reader in readers:
                hresult, card_status = SCardGetStatusChange(context, 1000, [(reader, SCARD_STATE_UNAWARE)])
                if hresult != SCARD_S_SUCCESS:
                    continue

                reader_state = card_status[0][1]

                # カードが検出された場合
                if reader_state & SCARD_STATE_PRESENT:
                    hresult, card, protocol = SCardConnect(context, reader, SCARD_SHARE_SHARED, SCARD_PROTOCOL_T0 | SCARD_PROTOCOL_T1)
                    if hresult == SCARD_S_SUCCESS:
                        try:
                            serial_number = get_card_serial_number(card)
                            on_card_touched(serial_number)
                        finally:
                            SCardDisconnect(card, SCARD_UNPOWER_CARD)
            time.sleep(0.5)
    except Exception as e:
        print(f"エラーが発生しました: {e}")

def get_card_serial_number(card):
    """カードのシリアル番号を取得して10進数に変換"""
    APDU_GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
    hresult, response = SCardTransmit(card, SCARD_PCI_T1, APDU_GET_UID)
    if hresult != SCARD_S_SUCCESS:
        raise Exception(f"シリアル番号の取得に失敗しました: {SCardGetErrorMessage(hresult)}")
    hex_serial = smartcard.util.toHexString(response[:-2]).replace(" ", "")
    return int(hex_serial, 16)