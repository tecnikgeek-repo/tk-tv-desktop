"""Schermate secondarie: Impostazioni (link della lista) e Informazioni."""
import platform
import sys

from PySide6.QtCore import QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

from tktv import APP_TITLE, AUTHOR_URL, VERSION
from tktv import style as S
from tktv.channels import Header, header_button
from tktv.icon import badge_pixmap
from tktv.util import resource_path

COMPUTER = "Mac" if sys.platform == "darwin" else "PC"


def _card(parent=None):
    w = QWidget(parent)
    w.setObjectName("card")
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    lay = QVBoxLayout(w)
    lay.setContentsMargins(24, 20, 24, 22)
    lay.setSpacing(12)
    return w, lay


def _card_label(text, glyph):
    row = QHBoxLayout()
    row.setSpacing(8)
    ic = QLabel(glyph)
    ic.setFont(S.icon_font(15))
    ic.setStyleSheet(f"color:{S.ACCENT};")
    lab = QLabel(text.upper())
    lab.setObjectName("cardLabel")
    row.addWidget(ic)
    row.addWidget(lab)
    row.addStretch(1)
    return row


def _avviso_liste():
    """Riquadro ambra «tk-tv è solo un lettore … Siamo contro la pirateria» sotto il link della lista."""
    from tktv.pro import AVVISO_FINE, AVVISO_TESTO, AVVISO_TITOLO
    w = QWidget()
    w.setObjectName("avvisoListe")
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    w.setStyleSheet(f"#avvisoListe {{ background:rgba(245,158,11,0.10); border:1px solid rgba(245,158,11,0.40);"
                    " border-radius:14px; }")
    riga = QHBoxLayout(w)
    riga.setContentsMargins(16, 14, 16, 14)
    riga.setSpacing(14)
    ic = QLabel(S.ICO_WARN)
    ic.setFont(S.icon_font(20))
    ic.setFixedSize(42, 42)
    ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
    ic.setStyleSheet(f"color:{S.AMBER}; background:rgba(245,158,11,0.18); border-radius:12px;")
    riga.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
    col = QVBoxLayout()
    col.setSpacing(4)
    t = QLabel(AVVISO_TITOLO)
    t.setStyleSheet("color:#ffffff; font-size:14px; font-weight:800; background:transparent;")
    s = QLabel(f"{AVVISO_TESTO}<br><b style='color:{S.AMBER};'>{AVVISO_FINE}</b>")
    s.setTextFormat(Qt.TextFormat.RichText)
    s.setWordWrap(True)
    s.setStyleSheet("color:#cbd5e1; font-size:13px; background:transparent;")
    col.addWidget(t)
    col.addWidget(s)
    riga.addLayout(col, 1)
    return w


def _passo(glyph, titolo, testo):
    """Un passo della card «Come funziona»: icona in un riquadro colorato, titolo e una riga di spiegazione."""
    w = QWidget()
    w.setObjectName("passo")
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    w.setStyleSheet(f"#passo {{ background:{S.NAVY}; border:1px solid {S.NAVY3}; border-radius:14px; }}")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(16, 16, 16, 16)
    lay.setSpacing(8)
    ic = QLabel(glyph)
    ic.setFont(S.icon_font(20))
    ic.setFixedSize(44, 44)
    ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
    ic.setStyleSheet(f"color:{S.ACCENT_L}; background:rgba(225,29,72,0.16); border-radius:12px;")
    t = QLabel(titolo)
    t.setStyleSheet("color:#ffffff; font-size:14px; font-weight:800; background:transparent;")
    s = QLabel(testo)
    s.setWordWrap(True)
    s.setObjectName("muted")
    s.setStyleSheet("background:transparent;")
    lay.addWidget(ic)
    lay.addWidget(t)
    lay.addWidget(s)
    lay.addStretch(1)
    return w


def _page_with_header(title, subtitle, on_back):
    page = QWidget()
    root = QVBoxLayout(page)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)
    header = Header(title, subtitle)
    back = header_button(S.ICO_BACK, "Indietro (Esc)")
    back.clicked.connect(on_back)
    header.row.insertWidget(0, back)
    root.addWidget(header)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setStyleSheet(f"QScrollArea, QScrollArea > QWidget > QWidget {{ background:{S.NAVY}; }}")
    inner = QWidget()
    body = QVBoxLayout(inner)
    body.setContentsMargins(28, 26, 28, 26)
    body.setSpacing(18)
    scroll.setWidget(inner)
    root.addWidget(scroll, 1)
    return page, header, back, body


# ---------------------------------------------------------------- Impostazioni
class SettingsPage(QWidget):
    save = Signal(str)
    back = Signal()
    resume_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        page, self.header, self.back_btn, body = _page_with_header("Impostazioni", "Lista dei canali", self.back)
        QVBoxLayout(self).setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(page)

        col = QVBoxLayout()
        col.setSpacing(18)
        wrap = QHBoxLayout()
        wrap.addStretch(1)
        wrap.addLayout(col, 0)
        wrap.addStretch(1)
        body.addLayout(wrap)

        logo = QLabel()
        logo.setPixmap(badge_pixmap(76, 22))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(logo)
        title = QLabel(APP_TITLE)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:24px; font-weight:800;")
        col.addWidget(title)
        self.lead = QLabel("")
        self.lead.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lead.setObjectName("soft")
        col.addWidget(self.lead)

        card, lay = _card()
        card.setFixedWidth(620)
        lay.addLayout(_card_label("Link della tua lista", S.ICO_LINK))
        row = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("http://…/playlist.m3u")
        self.url.returnPressed.connect(self._save)
        browse = QPushButton("Sfoglia…")
        browse.setToolTip(f"Scegli un file .m3u sul {COMPUTER}")
        browse.clicked.connect(self._browse)
        row.addWidget(self.url, 1)
        row.addWidget(browse)
        lay.addLayout(row)
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.hide()
        lay.addWidget(self.error)
        self.ok = QPushButton("Carica canali")
        self.ok.setObjectName("accent")
        self.ok.setMinimumHeight(46)
        self.ok.clicked.connect(self._save)
        lay.addWidget(self.ok)
        # responsabilità della lista: sempre visibile, anche a chi ha già chiuso il benvenuto
        lay.addWidget(_avviso_liste())
        col.addWidget(card)
        col.addWidget(self._come_funziona())

        card3, lay3 = _card()
        card3.setFixedWidth(620)
        lay3.addLayout(_card_label("All'avvio", S.ICO_HISTORY))
        self.resume = QCheckBox("Riparti dall'ultimo canale che stavi guardando")
        from tktv.tk_licenza_qt import stile_casella
        self.resume.setStyleSheet(stile_casella())   # casella ben visibile su fondo scuro, come quella delle statistiche
        self.resume.setCursor(Qt.CursorShape.PointingHandCursor)
        self.resume.toggled.connect(self.resume_changed)
        lay3.addWidget(self.resume)
        col.addWidget(card3)

        # statistiche anonime: solo col consenso (lo stesso della finestra di benvenuto)
        card5, lay5 = _card()
        card5.setFixedWidth(620)
        lay5.addLayout(_card_label("Privacy", S.ICO_INFO))
        from tktv import pro
        self.stats = pro.casella_statistiche()
        self.stats.setCursor(Qt.CursorShape.PointingHandCursor)
        lay5.addWidget(self.stats)
        stats_txt = QLabel(self.stats.toolTip())
        stats_txt.setWordWrap(True)
        stats_txt.setObjectName("muted")
        lay5.addWidget(stats_txt)
        col.addWidget(card5)

        # caffè: sempre ben visibile nelle Impostazioni (come la card «Offrimi un caffè» dei plugin TK)
        card4, lay4 = _card()
        self.coffee_card = card4  # nascosta a chi ha già donato (vedi showEvent)
        card4.setFixedWidth(620)
        lab = QLabel("OFFRIMI UN CAFFÈ")
        lab.setStyleSheet(f"color:{S.AMBER}; font-size:12px; font-weight:800; letter-spacing:1px;")
        lay4.addWidget(lab)
        row4 = QHBoxLayout()
        row4.setSpacing(16)
        txt = QLabel(f"{APP_TITLE} è gratis. Se ti è utile, un caffè mi aiuta a migliorarlo e a crearne altri.")
        txt.setWordWrap(True)
        txt.setObjectName("soft")
        row4.addWidget(txt, 1)
        from tktv.tk_licenza_qt import pulsante_caffe
        coffee = pulsante_caffe(pro.licenza())
        if coffee is not None:
            coffee.setMinimumHeight(44)
            coffee.setMinimumWidth(190)
            row4.addWidget(coffee)
        lay4.addLayout(row4)
        col.addWidget(card4)

        col.addStretch(1)
        self.url.textChanged.connect(self._refresh_button)
        self._initial = ""

    def prepare(self, url, can_go_back, error=None):
        self._initial = url
        self.url.setText(url)
        self.back_btn.setVisible(can_go_back)
        self.lead.setText("Modifica il link della tua lista quando vuoi" if url
                          else "Inserisci il link della tua lista M3U per iniziare")
        self.set_loading(False)
        self.set_error(error)
        QTimer.singleShot(0, self.url.setFocus)

    def showEvent(self, e):
        # chi ha una chiave delle versioni vecchie ha già donato: niente caffè
        from tktv import pro
        from tktv.tk_licenza_qt import ha_donato
        lic = pro.licenza()
        self.coffee_card.setVisible(not ha_donato(lic))
        # la scelta sulle statistiche può arrivare dalla finestra di benvenuto dopo che la pagina è stata creata
        self.stats.blockSignals(True)
        self.stats.setChecked(bool(lic is not None and lic.consenso_statistiche()))
        self.stats.blockSignals(False)
        super().showEvent(e)

    def set_resume(self, on):
        self.resume.blockSignals(True)
        self.resume.setChecked(bool(on))
        self.resume.blockSignals(False)

    def set_loading(self, loading):
        self.ok.setEnabled(not loading)
        self.url.setEnabled(not loading)
        if loading:
            self.ok.setText("Caricamento dei canali…")
        else:
            self._refresh_button()

    def set_error(self, text):
        self.error.setText(text or "")
        self.error.setVisible(bool(text))

    def _refresh_button(self):
        if not self.ok.isEnabled():
            return
        url = self.url.text().strip()
        if self._initial and url == self._initial.strip():
            self.ok.setText("Ricarica canali")
        elif self._initial:
            self.ok.setText("Salva e ricarica")
        else:
            self.ok.setText("Carica canali")

    def _come_funziona(self):
        """Card «Come funziona»: tre passi affiancati al posto della vecchia nota in grigio."""
        card, lay = _card()
        card.setFixedWidth(620)
        lay.addLayout(_card_label("Come funziona", S.ICO_INFO))
        riga = QHBoxLayout()
        riga.setSpacing(12)
        riga.addWidget(_passo(S.ICO_LINK, "Incolla il link", "Il link della tua lista, in formato .m3u o .m3u8."), 1)
        riga.addWidget(_passo(S.ICO_FOLDER, "Oppure un file", f"Hai la lista salvata? Scegli il file .m3u sul {COMPUTER}."), 1)
        riga.addWidget(_passo(S.ICO_LOCK, "Resta solo qui", f"Il link è salvato solo su questo {COMPUTER}: non va a nessun server."), 1)
        lay.addLayout(riga)
        return card

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Scegli la playlist", "", "Playlist (*.m3u *.m3u8);;Tutti i file (*)")
        if path:
            self.url.setText(path)

    def _save(self):
        url = self.url.text().strip()
        if url:
            self.set_error(None)
            self.save.emit(url)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape and self.back_btn.isVisible():
            self.back.emit()
            return
        super().keyPressEvent(e)


# ---------------------------------------------------------------- Informazioni
SHORTCUTS = [
    ("Clic sulla tessera / Invio", "Guarda il canale"),
    ("Clic destro", "Aggiungi o togli dai preferiti"),
    ("⌘F" if sys.platform == "darwin" else "Ctrl+F", "Cerca un canale"),
    ("↑ ↓  ·  PagSu PagGiù", "Canale precedente / successivo"),
    ("Numeri", "Vai al canale con quel numero"),
    ("F  ·  F11  ·  doppio clic", "Schermo intero"),
    ("Spazio", "Pausa / riprendi"),
    ("M  ·  rotellina  ·  + −", "Muto e volume"),
    ("R", "Aggiorna il flusso"),
    ("P", "Aggiungi/togli dai preferiti"),
    ("T", "Timer di spegnimento: 30, 60, 90, 120 minuti"),
    ("A", "Lingua dell'audio (canali con più lingue)"),
    ("Esc", "Esci da schermo intero / torna ai canali"),
]


class InfoPage(QWidget):
    back = Signal()
    check_updates = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        page, self.header, self.back_btn, body = _page_with_header("Informazioni", f"{APP_TITLE} per {'Mac' if sys.platform == 'darwin' else 'Windows'}", self.back)
        QVBoxLayout(self).setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(page)

        cols = QHBoxLayout()
        cols.setSpacing(20)
        body.addLayout(cols)
        main = QVBoxLayout()
        main.setSpacing(20)
        side = QVBoxLayout()
        side.setSpacing(20)
        cols.addLayout(main, 1)
        cols.addLayout(side, 0)

        # presentazione
        card, lay = _card()
        top = QHBoxLayout()
        top.setSpacing(16)
        ic = QLabel()
        ic.setPixmap(badge_pixmap(64, 18))
        top.addWidget(ic)
        t = QLabel(f"<div style='font-size:24px;font-weight:800'>{APP_TITLE}</div>"
                   f"<div style='color:{S.GRAY300}'>Il player per la TV in diretta della tua lista M3U</div>")
        top.addWidget(t, 1)
        lay.addLayout(top)
        feats = QLabel("<ul style='margin-left:-20px; line-height:160%'>"
                       "<li>Canali raggruppati, generalisti in evidenza e preferiti</li>"
                       "<li>Loghi dei canali, ricerca istantanea e numero canale da tastiera</li>"
                       "<li>Preferiti, timer di spegnimento e lingua dell'audio</li>"
                       "<li>App e pay TV a portata di clic (si aprono nel browser)</li>"
                       "<li>Si aggiorna da solo quando esce una nuova versione</li></ul>")
        feats.setObjectName("soft")
        feats.setWordWrap(True)
        lay.addWidget(feats)
        main.addWidget(card)

        # scorciatoie
        card, lay = _card()
        lay.addLayout(_card_label("Tastiera e mouse", S.ICO_LIST))
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(8)
        for i, (keys, what) in enumerate(SHORTCUTS):
            k = QLabel(keys)
            k.setStyleSheet(f"color:{S.WHITE}; font-weight:700;")
            w = QLabel(what)
            w.setObjectName("soft")
            grid.addWidget(k, i, 0)
            grid.addWidget(w, i, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        main.addWidget(card)
        main.addStretch(1)

        # sidebar TecnikGeek
        card, lay = _card()
        card.setFixedWidth(280)
        lab = QLabel("CREATO DA")
        lab.setObjectName("cardLabel")
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lab)
        logo = QLabel()
        logo.setFixedSize(80, 80)
        pm = QPixmap(resource_path("assets/tecnikgeek-logo.png"))
        if not pm.isNull():
            logo.setPixmap(_rounded(pm, 80, 20))
        lay.addWidget(logo, 0, Qt.AlignmentFlag.AlignCenter)
        name = QLabel("<div style='font-size:18px;font-weight:800'>TecnikGeek</div>")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(name)
        help_ = QLabel("Ti serve assistenza?")
        help_.setAlignment(Qt.AlignmentFlag.AlignCenter)
        help_.setObjectName("soft")
        lay.addWidget(help_)
        contact = QPushButton("Contattami")
        contact.setObjectName("accent")
        contact.setMinimumHeight(44)
        contact.setCursor(Qt.CursorShape.PointingHandCursor)
        contact.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(AUTHOR_URL + "/contatti/")))
        lay.addWidget(contact)
        side.addWidget(card)


        card, lay = _card()
        card.setFixedWidth(280)
        lay.addLayout(_card_label("Informazioni", S.ICO_INFO))
        self.info_grid = QGridLayout()
        self.info_grid.setVerticalSpacing(8)
        lay.addLayout(self.info_grid)
        free = QLabel("Software libero · AGPL-3.0")
        free.setObjectName("soft")
        free.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(free)
        lic_btn = QPushButton("Licenze e codice sorgente")
        lic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        lic_btn.clicked.connect(self._licenze)
        lay.addWidget(lic_btn)
        from tktv import pro
        from tktv.tk_licenza_qt import pulsante_caffe
        self.coffee_btn = pulsante_caffe(pro.licenza())
        if self.coffee_btn is not None:
            self.coffee_btn.setMinimumHeight(44)
            lay.addWidget(self.coffee_btn)
        upd = QPushButton("Controlla aggiornamenti")
        upd.clicked.connect(self.check_updates)
        lay.addWidget(upd)
        side.addWidget(card)
        side.addStretch(1)
        self._fill_info()

    def _licenze(self):
        from tktv import pro
        pro.mostra_licenze(self)

    def _fill_info(self):
        try:
            from tktv import engine
            vlc = engine.load()
            vlc_ver = vlc.libvlc_get_version().decode().split(" ")[0]
        except Exception:
            vlc_ver = "non trovato"
        rows = [
            ("Versione", VERSION),
            ("Licenza", "AGPL-3.0"),
            ("Motore video", f"VLC {vlc_ver}"),
            ("Python", platform.python_version()),
            ("macOS", f"{platform.mac_ver()[0]} ({platform.machine()})") if sys.platform == "darwin"
            else ("Windows", f"{platform.release()} ({platform.version()})"),
        ]
        for i, (k, v) in enumerate(rows):
            a = QLabel(k)
            a.setObjectName("muted")
            b = QLabel(v)
            b.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.info_grid.addWidget(a, i, 0)
            self.info_grid.addWidget(b, i, 1)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.back.emit()
            return
        super().keyPressEvent(e)


def _rounded(pm, size, radius):
    ratio = 2
    img = QImage(size * ratio, size * ratio, QImage.Format.Format_ARGB32)
    img.setDevicePixelRatio(ratio)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    from PySide6.QtGui import QPainterPath
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(QRectF(0, 0, size, size), pm, QRectF(pm.rect()))
    p.end()
    return QPixmap.fromImage(img)
