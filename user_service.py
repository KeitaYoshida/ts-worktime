import requests

from db import fetch_user_data, update_user_serial
from logger import logger


def sync_user_data(config):
    """サーバーから最新ユーザーを取得してローカルへ反映する"""
    return fetch_user_data(config)


def register_user_card(config, user_id, serial_number):
    """カード情報をサーバーとローカルDBへ反映する"""
    endpoint = f"{config['set_user_serial']}/{user_id}"
    payload = {"serial": serial_number}

    try:
        response = requests.post(endpoint, json=payload, timeout=10)
        if response.status_code != 200:
            logger.error(
                "ユーザーカード登録APIが失敗しました: status=%s user_id=%s",
                response.status_code,
                user_id,
            )
            return False, f"ユーザー登録APIエラー: {response.status_code}"
    except requests.Timeout:
        logger.error("ユーザーカード登録APIがタイムアウトしました")
        return False, "ユーザー登録APIがタイムアウトしました"
    except requests.RequestException as exc:
        logger.error("ユーザーカード登録APIで通信エラー: %s", exc)
        return False, f"ユーザー登録API通信エラー: {exc}"

    if not update_user_serial(user_id, serial_number):
        logger.error("ローカルDBへのカード反映に失敗しました: user_id=%s", user_id)
        return False, "ローカルDBへの反映に失敗しました"

    logger.info("カード登録完了: user_id=%s serial=%s", user_id, serial_number)
    return True, None
