# -*- mode: python -*-
# PyInstaller: crea "TK TV.app" per macOS. Uso: pyinstaller --noconfirm --clean mac/tk-tv-mac.spec
# libVLC NON passa da PyInstaller: build_mac.sh la copia con ditto in Contents/Frameworks/vlc
# (date dei file intatte, altrimenti plugins.dat non vale e l'avvio scansiona tutti i plugin).
import os
import re

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
with open(os.path.join(ROOT, "tktv", "__init__.py"), encoding="utf-8") as fh:
    VERSION = re.search(r'VERSION = "(.+)"', fh.read()).group(1)

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    hiddenimports=["vlc", "certifi", "tktv.pro", "tktv.tk_licenza", "tktv.tk_licenza_qt", "tktv.tk_aggiornamento",
                   "tktv.dashfix"],
    datas=[
        (os.path.join(ROOT, "assets", "tecnikgeek-logo.png"), "assets"),
        (os.path.join(ROOT, "assets", "tk-tv.png"), "assets"),
        (os.path.join(ROOT, "assets", "fonts"), os.path.join("assets", "fonts")),
        # testi delle licenze preparati da build_mac.sh (installer/licenze.py): Informazioni > Licenze
        (os.path.join(ROOT, "build-licenze", "licenze"), "licenze"),
    ],
    excludes=["tkinter", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore", "PySide6.QtMultimedia",
              "PySide6.QtPdf", "PySide6.QtOpenGL"],
)

# componenti Qt non usati da un'app a widget
DROP = ("QtQuick", "QtQml", "QtVirtualKeyboard", "QtPdf", "libqpdf", "QtWebEngine", "Qt3D", "QtMultimedia",
        "QtOpenGL")
a.binaries = [b for b in a.binaries if not any(k in b[0] for k in DROP)]
a.datas = [d for d in a.datas if not any(k in d[0] for k in DROP)]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TK TV", console=False, argv_emulation=False)
coll = COLLECT(exe, a.binaries, a.datas, name="TK TV")
app = BUNDLE(
    coll,
    name="TK TV.app",
    icon=os.path.join(ROOT, "assets", "tk-tv.icns"),
    bundle_identifier="it.pietrodefilippis.tktv",
    version=VERSION,
    info_plist={
        "CFBundleName": "TK TV",
        "CFBundleDisplayName": "TK TV",
        # il bundle resta «TK TV.app» (lo script di aggiornamento delle versioni installate cerca quel nome nel dmg):
        # il nome visibile «tk-tv» (Finder, Dock, menu) arriva dai InfoPlist.strings che build_mac.sh mette in *.lproj
        "LSHasLocalizedDisplayName": True,
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "TecnikGeek - pietrodefilippis.it",
        "LSApplicationCategoryType": "public.app-category.entertainment",
        "LSMinimumSystemVersion": "11.0",
        # i canali della playlist sono spesso http: senza questa chiave macOS li bloccherebbe (ATS)
        "NSAppTransportSecurity": {"NSAllowsArbitraryLoads": True},
    },
)
