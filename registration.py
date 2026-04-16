import threading


class RegistrationSession:
    """カード登録モードの選択状態を保持する"""

    def __init__(self):
        self._lock = threading.Lock()
        self._selected_user = None

    def select_user(self, user_id, user_name):
        with self._lock:
            self._selected_user = {
                "id": user_id,
                "name": user_name,
            }

    def clear(self):
        with self._lock:
            self._selected_user = None

    def is_active(self):
        with self._lock:
            return self._selected_user is not None

    def get_selected_user(self):
        with self._lock:
            if self._selected_user is None:
                return None
            return dict(self._selected_user)
