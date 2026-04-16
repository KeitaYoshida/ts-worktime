import time

try:
    import RPi.GPIO as GPIO
except Exception:
    GPIO = None

BUZZER_PIN = 18  # GPIO 18を使用

# 音符の周波数定義
NOTES = {
    'C4': 262,  # ド
    'D4': 294,  # レ
    'E4': 330,  # ミ
    'F4': 349,  # ファ
    'G4': 392,  # ソ
    'A4': 440,  # ラ
    'B4': 494,  # シ
    'C5': 523,  # 高いド
}

# デフォルトの音量 (0-100)
DEFAULT_VOLUME = 50
current_volume = DEFAULT_VOLUME
pwm = None

def setup_buzzer():
    """ブザーの初期化"""
    if GPIO is None:
        return
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUZZER_PIN, GPIO.OUT)
    GPIO.setwarnings(False)
    global pwm
    pwm = GPIO.PWM(BUZZER_PIN, 1000)  # PWM初期化（初期周波数1000Hz）
    pwm.start(0)  # デューティ比0%で開始

def cleanup_buzzer():
    """ブザーのクリーンアップ"""
    if GPIO is None or pwm is None:
        return
    try:
        pwm.stop()
        GPIO.cleanup(BUZZER_PIN)
    except:
        pass

def set_volume(volume):
    """
    音量を設定（0-100）
    Args:
        volume (int): 音量レベル（0-100）
    """
    global current_volume
    current_volume = max(0, min(100, volume))

def play_tone(frequency, duration):
    """
    指定された周波数と長さで音を鳴らす
    Args:
        frequency (int): 周波数（Hz）
        duration (float): 長さ（秒）
    """
    if GPIO is None or pwm is None:
        time.sleep(duration)
        return
    try:
        pwm.ChangeFrequency(frequency)
        # 音量に応じてデューティ比を調整（最大50%）
        duty = (current_volume / 100.0) * 30
        pwm.ChangeDutyCycle(duty)
        time.sleep(duration)
        pwm.ChangeDutyCycle(0)
    except Exception as e:
        print(f"音声出力エラー: {e}")

def beep(duration=0.1):
    """
    シンプルなビープ音を鳴らす
    Args:
        duration (float): 音の長さ（秒）
    """
    play_tone(2000, duration)

def play_success_melody():
    """成功時のメロディを再生（ピッ）"""
    play_tone(2000, 0.1)  # 単発のピッ音

def play_error_melody():
    """エラー時のメロディを再生（ピピッ）"""
    play_tone(1500, 0.08)  # 少し低い音で短く
    time.sleep(0.05)        # 少し間隔を空ける
    play_tone(1500, 0.08)  # 2回目のピッ音
