import platform


IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"


try:
    import sdnotify as _sdnotify
except Exception:
    _sdnotify = None


class NoopNotifier:
    def notify(self, _message):
        return False


def create_notifier():
    if _sdnotify is None:
        return NoopNotifier()
    return _sdnotify.SystemdNotifier()
