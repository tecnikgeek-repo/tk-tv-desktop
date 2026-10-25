"""Palette TK (base navy + accent rosa/rosso di tk-tv) e foglio di stile Qt. Tema scuro: è un player."""
import sys

from PySide6.QtGui import QFont, QFontDatabase

NAVY = "#0f172a"
NAVY2 = "#1e293b"
NAVY3 = "#334155"
ACCENT = "#e11d48"
ACCENT_D = "#be123c"
ACCENT_L = "#fb7185"
GREEN = "#10b981"
AMBER = "#f59e0b"
GRAY300 = "#cbd5e1"
GRAY500 = "#64748b"
WHITE = "#ffffff"

if sys.platform == "darwin":
    # Mac: Material Icons Round (Apache 2.0) incluso in assets/fonts
    ICON_FAMILY = "Material Icons Round"
    ICO_SEARCH = "\ue8b6"
    ICO_REFRESH = "\ue5d5"
    ICO_SETTINGS = "\ue8b8"
    ICO_INFO = "\ue88f"
    ICO_BACK = "\ue5c4"
    ICO_PREV = "\ue045"
    ICO_NEXT = "\ue044"
    ICO_FULL = "\ue5d0"
    ICO_UNFULL = "\ue5d1"
    ICO_VOLUME = "\ue050"
    ICO_MUTE = "\ue04f"
    ICO_STAR = "\ue83a"
    ICO_STAR_FILL = "\ue838"
    ICO_PLAY = "\ue037"
    ICO_PAUSE = "\ue034"
    ICO_TV = "\ue333"
    ICO_CLOSE = "\ue5cd"
    ICO_LINK = "\ue157"
    ICO_PHONE = "\ue32c"
    ICO_GLOBE = "\ue80b"
    ICO_LIST = "\ue241"
    ICO_APPS = "\ue5c3"
    ICO_FOLDER = "\ue2c8"
    ICO_UPDATE = "\ue2c4"
    ICO_MAP = "\ue55f"
    ICO_RADIO = "\ue03e"
    ICO_MOVIE = "\ue02c"
    ICO_KIDS = "\ueb41"
    ICO_NEWS = "\uef42"
    ICO_DOCS = "\ue80c"
    ICO_HEART = "\ue87d"
    ICO_TIMER = "\ue425"
    ICO_HISTORY = "\ue889"
    ICO_LANG = "\ue8e2"
    ICO_COFFEE = "\ue541"
    ICON_SCALE = 1.2
    UI_FAMILY = ".AppleSystemUIFont"
else:
    # Icone di sistema di Windows (Segoe Fluent Icons su Windows 11, MDL2 su Windows 10)
    ICON_FAMILY = None
    ICO_SEARCH = ""
    ICO_REFRESH = ""
    ICO_SETTINGS = ""
    ICO_INFO = ""
    ICO_BACK = ""
    ICO_PREV = ""
    ICO_NEXT = ""
    ICO_FULL = ""
    ICO_UNFULL = ""
    ICO_VOLUME = ""
    ICO_MUTE = ""
    ICO_STAR = ""
    ICO_STAR_FILL = ""
    ICO_PLAY = ""
    ICO_PAUSE = ""
    ICO_TV = ""
    ICO_CLOSE = ""
    ICO_LINK = ""
    ICO_PHONE = ""
    ICO_GLOBE = ""
    ICO_LIST = ""
    ICO_APPS = ""
    ICO_FOLDER = ""
    ICO_UPDATE = ""
    ICO_MAP = ""
    ICO_RADIO = ""   # Audio
    ICO_MOVIE = ""   # Video
    ICO_KIDS = ""    # People
    ICO_NEWS = ""    # Page
    ICO_DOCS = ""    # Library
    ICO_HEART = ""   # Heart
    ICO_TIMER = ""     # Clock
    ICO_HISTORY = ""   # History
    ICO_LANG = ""      # Characters
    ICO_COFFEE = ICO_HEART   # tra le icone di Windows non c'è la tazza
    ICON_SCALE = 1.0
    UI_FAMILY = "Segoe UI"


def icon_font(px=16):
    if ICON_FAMILY:
        name = ICON_FAMILY
    else:
        fams = set(QFontDatabase.families())
        name = "Segoe Fluent Icons" if "Segoe Fluent Icons" in fams else "Segoe MDL2 Assets"
    f = QFont(name)
    f.setPixelSize(round(px * ICON_SCALE))
    return f


def ui_font():
    """Font dell'interfaccia: Segoe UI su Windows, San Francisco su Mac."""
    return QFont(UI_FAMILY)


def load_fonts():
    """Registra i font inclusi nell'app (le icone su Mac). Da chiamare dopo aver creato QApplication."""
    import glob
    import os
    from tktv.util import resource_path
    for path in glob.glob(os.path.join(resource_path("assets"), "fonts", "*.otf")):
        QFontDatabase.addApplicationFont(path)


# il font dell'app si imposta con QApplication.setFont: una regola «font-family» qui
# sovrascriverebbe anche il font delle icone (quadratini al posto dei simboli)
QSS = f"""
QWidget {{ color: {WHITE}; }}
QMainWindow, #tkRoot {{ background: {NAVY}; }}
QToolTip {{ background: {NAVY2}; color: {WHITE}; border: 1px solid {NAVY3}; padding: 4px 8px; }}

#tkHeader {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {NAVY}, stop:0.6 {NAVY2}, stop:1 {NAVY3});
    border-bottom: 1px solid {NAVY3};
}}
#tkTitle {{ font-size: 21px; font-weight: 800; color: {WHITE}; }}
#tkSubtitle {{ color: {GRAY300}; font-size: 14px; }}

QPushButton {{
    background: {NAVY3}; color: {WHITE}; border: 0; border-radius: 8px;
    padding: 8px 18px; font-weight: 700;
}}
QPushButton:hover {{ background: #3f4f66; }}
QPushButton:disabled {{ color: {GRAY500}; background: {NAVY2}; }}
QPushButton#accent {{ background: {ACCENT}; }}
QPushButton#accent:hover {{ background: {ACCENT_D}; }}
QPushButton#accent:disabled {{ background: {NAVY3}; color: {GRAY500}; }}
QPushButton#flat {{ background: transparent; color: {GRAY300}; padding: 6px 10px; }}
QPushButton#flat:hover {{ color: {WHITE}; background: {NAVY2}; }}

QToolButton#headerAction {{
    background: transparent; border: 0; border-radius: 19px; color: {WHITE};
    min-width: 38px; min-height: 38px; max-width: 38px; max-height: 38px;
}}
QToolButton#headerAction:hover {{ background: rgba(255,255,255,0.10); }}
QToolButton#headerAction:checked {{ background: {ACCENT}; }}

QLineEdit {{
    background: {NAVY}; color: {WHITE}; border: 1px solid {NAVY3}; border-radius: 10px;
    padding: 9px 14px; selection-background-color: {ACCENT};
}}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
#searchBox {{ background: {NAVY2}; }}

#card {{ background: {NAVY2}; border-radius: 16px; }}
#cardLabel {{ color: {ACCENT}; font-size: 13px; font-weight: 800; letter-spacing: 1px; }}
#muted {{ color: {GRAY500}; }}
#soft {{ color: {GRAY300}; }}
#error {{ color: {ACCENT_L}; }}

QListWidget#sidebar {{
    background: {NAVY}; border: 0; border-right: 1px solid {NAVY2}; outline: 0; padding: 8px 6px;
}}
QListWidget#sidebar::item {{ background: transparent; border: 0; }}  /* voci disegnate da SidebarDelegate */

QListView#grid {{ background: {NAVY}; border: 0; outline: 0; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {NAVY3}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {GRAY500}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {NAVY3}; border-radius: 4px; min-width: 30px; }}

QSlider::groove:horizontal {{ height: 4px; background: rgba(255,255,255,0.25); border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {WHITE}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}

QMenu {{ background: {NAVY2}; border: 1px solid {NAVY3}; padding: 6px; }}
QMenu::item {{ padding: 7px 22px 7px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT}; }}

QDialog {{ background: {NAVY}; }}
QProgressBar {{ background: {NAVY2}; border: 0; border-radius: 4px; }}
QProgressBar::chunk {{ border-radius: 4px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {NAVY3}, stop:1 {ACCENT}); }}
QCheckBox {{ spacing: 8px; }}
QMessageBox QLabel {{ color: {WHITE}; }}
"""
