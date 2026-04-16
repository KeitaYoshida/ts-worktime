import sqlite3
import json
import requests
from datetime import datetime
import logging

DB_FILE = "attendance.db"
logger = logging.getLogger(__name__)


def initialize_db():
    """SQLiteデータベースの初期化"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # attendance テーブル
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        serial_number TEXT,
        timestamp TEXT,
        state TEXT,
        back_user_id TEXT,
        user_name TEXT,
        login_id TEXT,
        marge INTEGER CHECK (marge IN (0, 1, 2))
    )
    """)

    # users テーブル
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        res_user_id TEXT UNIQUE,
        login_id TEXT,
        name TEXT,
        id_serial TEXT
    )
    """)

    conn.commit()
    conn.close()


def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # dict形式で取得できるようにする
    return conn


def insert_user_data(user_data):
    """
    サーバーから取得したユーザーデータで、Users テーブルに登録・更新する
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # トランザクション開始
        cursor.execute("BEGIN TRANSACTION")
        
        for user in user_data:
            try:
                cursor.execute("""
                INSERT INTO users (res_user_id, login_id, name, id_serial)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(res_user_id) DO UPDATE SET
                    login_id = excluded.login_id,
                    name = excluded.name,
                    id_serial = excluded.id_serial
                """, (
                    user.get("id"),
                    user.get("loginid"),
                    user.get("name"),
                    user.get("serial")
                ))
            except sqlite3.Error as e:
                logger.error(f"ユーザーデータの登録中にエラーが発生: {e}")
                raise
        
        # トランザクションをコミット
        conn.commit()
        logger.info(f"ユーザーデータの登録・更新が完了しました（{len(user_data)}件）")
        
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"ユーザーデータの登録・更新に失敗: {e}")
        raise
    finally:
        if conn:
            conn.close()


def fetch_user_data(config):
    """
    サーバーからユーザー情報を取得し、ローカルに保存
    """
    try:
        logger.info("ユーザー情報の取得を開始します...")
        api_url = config.get('user_list_api')
        if not api_url:
            logger.error("user_list_apiが設定されていません")
            return None

        logger.debug(f"APIエンドポイント: {api_url}")
        response = requests.get(api_url, timeout=10)  # タイムアウトを10秒に設定

        if response.status_code == 200:
            user_data = response.json()
            logger.info(f"ユーザー情報を取得しました（{len(user_data)}件）")
            
            # 取得したデータの内容をログに出力
            for user in user_data:
                logger.debug(f"ユーザー情報: ID={user.get('id')}, 名前={user.get('name')}, シリアル={user.get('serial')}")

            # 取得したデータをJSONファイルにも保存
            try:
                json_file = config.get('user_data_file', 'user_data.json')
                logger.debug(f"JSONファイルに保存: {json_file}")
                with open(json_file, 'w') as f:
                    json.dump(user_data, f, indent=2, ensure_ascii=False)
                logger.debug("ユーザーデータをJSONファイルに保存しました")
            except Exception as e:
                logger.error(f"JSONファイルの保存に失敗: {e}")

            # ユーザーデータをDBに登録
            try:
                insert_user_data(user_data)
                logger.info("ユーザーデータをデータベースに登録しました")
                return user_data
            except Exception as e:
                logger.error(f"データベースへの登録に失敗: {e}")
                return None
        else:
            logger.error(f"APIリクエストが失敗しました（ステータスコード: {response.status_code}）")
            return None

    except requests.Timeout:
        logger.error("APIリクエストがタイムアウトしました")
        return None
    except requests.RequestException as e:
        logger.error(f"APIリクエスト中にエラーが発生: {e}")
        return None
    except Exception as e:
        logger.error(f"予期せぬエラーが発生: {e}")
        return None


def get_user_by_serial(serial_number):
    """
    usersテーブルからシリアル番号を検索
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT res_user_id, name FROM users WHERE id_serial = ?", (serial_number,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {"res_user_id": result[0], "name": result[1]}
    return None


def save_to_db(serial_number, state, user_info):
    """
    シリアル番号、状態、現在時刻、ユーザー情報をデータベースに保存し、登録情報を返す
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()

    print(user_info)
    # データベースに保存
    cursor.execute("""
    INSERT INTO attendance (serial_number, timestamp, state, back_user_id, user_name, login_id)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        serial_number,
        timestamp,
        state,
        user_info.get("res_user_id"),
        user_info.get("name"),
        user_info.get("login_id")
    ))

    # 最後に挿入されたIDを取得
    record_id = cursor.lastrowid

    conn.commit()
    conn.close()

    # 保存完了メッセージ
    print(f"記録: シリアル番号={serial_number}, 時刻={timestamp}, 状態={state}, ユーザーID={user_info.get('res_user_id')}")

    # 保存した情報を辞書形式で返す
    return {
        "id": record_id,
        "serial_number": serial_number,
        "timestamp": timestamp,
        "state": state,
        "user_id": user_info.get("res_user_id"),
        "user_name": user_info.get("name"),
        "login_id": user_info.get("login_id")
    }


def update_attendance(record_id, column_name, value):
    """
    指定されたIDのattendanceレコードの特定カラムを更新する

    Args:
        record_id (int): 更新するレコードのID
        column_name (str): 更新するカラム名
        value (any): 更新する値
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # SQLインジェクション対策としてカラム名をバリデーション
    valid_columns = ["serial_number", "timestamp", "state", "back_user_id", "user_name", "login_id", "marge"]
    if column_name not in valid_columns:
        raise ValueError(f"無効なカラム名です: {column_name}")

    try:
        # SQLクエリの動的生成
        sql = f"UPDATE attendance SET {column_name} = ? WHERE id = ?"
        cursor.execute(sql, (value, record_id))

        conn.commit()
        print(f"レコードID={record_id} の {column_name} を {value} に更新しました。")

    except sqlite3.Error as e:
        print(f"データベースエラー: {e}")
    finally:
        conn.close()