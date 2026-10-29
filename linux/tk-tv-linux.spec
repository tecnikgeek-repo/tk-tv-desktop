# -*- mode: python -*-
# PyInstaller: crea la cartella «dist/tk-tv» per Linux, poi build_linux.sh ci aggiunge libVLC (vlc/) e la mette
# nell'AppImage. Uso: pyinstaller --noconfirm --clean linux/tk-tv-linux.spec
# libVLC NON passa da PyInstaller: linux/includi_vlc.py la prepara (pacchetti Ubuntu, RUNPATH relativo, cache dei
# plugin) e build_linux.sh la copia con «cp -a» (date intatte: plugins.dat resta valido).
import glob
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
with open(os.path.join(ROOT, "tktv", "__init__.py"), encoding="utf-8") as fh:
    VERSION = re.search(r'VERSION = "(.+)"', fh.read()).group(1)

# librerie xcb che servono a Qt sotto X11/XWayland e non ci sono su ogni Ubuntu (libxcb-cursor…): accanto alle
# librerie di Qt, dove le trova libQt6XcbQpa (RUNPATH $ORIGIN)
QT_XCB = [(f, os.path.join("PySide6", "Qt", "lib")) for f in sorted(glob.glob(os.path.join(ROOT, "build", "qt-xcb", "*")))]

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    binaries=QT_XCB,
    hiddenimports=["vlc", "certifi", "tktv.pro", "tktv.tk_licenza", "tktv.tk_licenza_qt", "tktv.tk_aggiornamento",
                   "tktv.tk_linux", "tktv.dashfix", "tktv.selftest_video", "jeepney", "jeepney.io.blocking",
                   "jeepney.wrappers"],
    datas=[
        (os.path.join(ROOT, "assets", "tecnikgeek-logo.png"), "assets"),
        (os.path.join(ROOT, "assets", "tk-tv.png"), "assets"),
        (os.path.join(ROOT, "build", "tk-tv-512.png"), "assets"),
        (os.path.join(ROOT, "assets", "fonts"), os.path.join("assets", "fonts")),
        # testi delle licenze preparati da build_linux.sh (installer/licenze.py + includi_vlc.py)
        (os.path.join(ROOT, "build-licenze", "licenze"), "licenze"),
    ],
    excludes=["tkinter", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore", "PySide6.QtMultimedia",
              "PySide6.QtPdf", "PySide6.QtOpenGL"],
)

# componenti Qt non usati da un'app a widget, e i plugin di piattaforma per schermi senza desktop
# (libqgtk3 porterebbe GTK della macchina di build; libvlc del sistema, se c'è: si usa solo quella in vlc/)
DROP = ("QtQuick", "QtQml", "QtVirtualKeyboard", "QtPdf", "libqpdf", "QtWebEngine", "Qt3D", "QtMultimedia",
        "QtOpenGL", "EglFs", "eglfs", "libqlinuxfb", "libqvnc", "libqvkkhrdisplay", "libqminimalegl",
        "libqtuiotouchplugin", "libqevdev", "libqlibinput", "libqgtk3", "libvlc.so", "libvlccore.so")
a.binaries = [b for b in a.binaries if not any(k in b[0] for k in DROP)]
a.datas = [d for d in a.datas if not any(k in d[0] for k in DROP)]

# Librerie del sistema di build: PyInstaller le copia tutte in _internal e il programma parte con
# LD_LIBRARY_PATH=_internal, quindi una libstdc++ o una GLib vecchie verrebbero usate anche dai driver del sistema
# (OpenGL di VLC). Come linuxdeploy: restano fuori le librerie «di base» (linux/includi_vlc.py, SO_BASE) e quelle
# che servivano solo a loro.
sys.path.insert(0, os.path.join(ROOT, "linux"))
from includi_vlc import di_base, elf_info  # noqa: E402


def _dipendenza_di_sistema(b):
    """Libreria presa dal sistema di build e messa in _internal solo perché un'altra la chiede."""
    nome, src = b[0], b[1]
    return ("/" not in nome and nome.startswith("lib") and not nome.startswith("libpython")
            and os.path.realpath(src).startswith(("/lib/", "/lib64/", "/usr/lib/", "/usr/lib64/", "/usr/local/lib/")))


per_nome = {os.path.basename(b[0]): b for b in a.binaries}
tenuti = {os.path.basename(b[0]) for b in a.binaries if not _dipendenza_di_sistema(b)}
coda = list(tenuti)
while coda:
    nome = coda.pop()
    b = per_nome.get(nome)
    info = elf_info(b[1]) if b is not None and b[2] != "SYMLINK" and os.path.isfile(b[1]) else None
    for so in (info[0] if info else []):
        if so in per_nome and so not in tenuti and not di_base(so):
            tenuti.add(so)
            coda.append(so)
tolti = sorted(n for n in per_nome if n not in tenuti)
print("   librerie del sistema di build lasciate fuori:", " ".join(tolti))
a.binaries = [b for b in a.binaries if os.path.basename(b[0]) in tenuti]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="tk-tv", console=False, strip=False)
coll = COLLECT(exe, a.binaries, a.datas, name="tk-tv")
