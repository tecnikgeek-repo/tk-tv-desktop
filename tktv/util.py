"""Funzioni di supporto: percorsi e dimensioni."""
import os
import sys


def app_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def profile_name():
    """Nome del profilo impostazioni. I test impostano TKTV_PROFILE per non toccare quelle reali dell'utente."""
    suffix = os.environ.get("TKTV_PROFILE", "").strip()
    return f"tk-tv-player-{suffix}" if suffix else "tk-tv-player"


def app_data_dir():
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, profile_name())
    os.makedirs(path, exist_ok=True)
    return path


def is_mac():
    return sys.platform == "darwin"


def resource_path(rel):
    return os.path.join(app_root(), rel)


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024.0
