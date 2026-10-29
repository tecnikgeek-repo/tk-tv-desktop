"""Funzioni di supporto: percorsi e dimensioni (Windows, Mac e Linux)."""
import os
import sys

IS_LINUX = sys.platform.startswith("linux")


def app_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def profile_name():
    """Nome del profilo impostazioni. I test impostano TKTV_PROFILE per non toccare quelle reali dell'utente."""
    suffix = os.environ.get("TKTV_PROFILE", "").strip()
    return f"tk-tv-player-{suffix}" if suffix else "tk-tv-player"


def app_data_dir():
    """Dati dell'utente. Windows: APPDATA; Mac: Libreria/Application Support; Linux: ~/.local/share
    (gli aggiornamenti non la toccano)."""
    if sys.platform == "darwin":
        path = os.path.join(os.path.expanduser("~/Library/Application Support"), profile_name())
    elif IS_LINUX:
        from tktv import tk_linux
        path = tk_linux.cartella_dati(profile_name())
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


# --------------------------------------------------------------------------- solo Linux
LINUX_DESKTOP_ID = "tk-tv"  # nome del file .desktop = app_id/WM_CLASS della finestra (icona nella barra)


def install_linux_menu():
    """Linux: voce «tk-tv» nel menu delle applicazioni con l'icona (si corregge da sola se l'AppImage si sposta)."""
    from tktv import APP_TITLE, tk_linux
    icona = resource_path(os.path.join("assets", "tk-tv-512.png"))  # creata da linux/build_linux.sh
    if not os.path.isfile(icona):
        icona = resource_path(os.path.join("assets", "tk-tv.png"))
    return tk_linux.installa_menu(
        LINUX_DESKTOP_ID, APP_TITLE, "Lettore della TV in diretta dalla tua lista M3U (TecnikGeek)",
        "AudioVideo;Video;Player;TV;", icona,
        nome_generico="Lettore TV", parole="tv;m3u;iptv;canali;diretta;lista;")
