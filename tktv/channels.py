"""Schermata canali: testata TK, barra laterale con le sezioni e griglia di tessere con i loghi."""
import sys

from PySide6.QtCore import QAbstractListModel, QEvent, QModelIndex, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem, QMenu,
    QStyle, QStyledItemDelegate, QToolButton, QVBoxLayout, QWidget,
)

from tktv import APP_TITLE
from tktv import style as S
from tktv.icon import badge_pixmap
from tktv.playlist import Channel, generalisti
from tktv.streaming import CATALOGO, AppStreaming

TILE = QSize(176, 166)
GROUP_TITLE_H = 50


class GroupTitle:
    """Titolo di gruppo dentro la griglia di «Tutti i canali» (occupa una riga intera, come nell'app Android)."""

    def __init__(self, label, count):
        self.label = label
        self.count = count


def header_button(glyph, tip, parent=None):
    b = QToolButton(parent)
    b.setObjectName("headerAction")
    b.setText(glyph)
    b.setFont(S.icon_font(16))
    b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    return b


class Header(QWidget):
    """Testata navy TK con icona, titolo, sottotitolo e azioni a destra."""

    def __init__(self, title=APP_TITLE, subtitle="", parent=None):
        super().__init__(parent)
        self.setObjectName("tkHeader")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(22, 14, 18, 14)
        self.row.setSpacing(12)
        ic = QLabel()
        ic.setPixmap(badge_pixmap(42))
        ic.setFixedSize(42, 42)
        self.row.addWidget(ic, 0, Qt.AlignmentFlag.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = QLabel(title)
        self.title.setObjectName("tkTitle")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("tkSubtitle")
        col.addWidget(self.title)
        col.addWidget(self.subtitle)
        self.row.addLayout(col)
        self.row.addStretch(1)


# ---------------------------------------------------------------- modello e disegno delle tessere
class TileModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []

    def set_items(self, items):
        self.beginResetModel()
        self.items = list(items)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self.items[index.row()]
        if isinstance(item, GroupTitle):
            return item if role == Qt.ItemDataRole.UserRole else (item.label if role == Qt.ItemDataRole.DisplayRole else None)
        if role == Qt.ItemDataRole.DisplayRole:
            return item.nome if isinstance(item, AppStreaming) else item.name
        if role == Qt.ItemDataRole.ToolTipRole:
            if isinstance(item, AppStreaming):
                return f"{item.nome} — si apre nel browser"
            return f"[{item.number}] {item.name}" + (f"\n{item.group}" if item.group else "")
        if role == Qt.ItemDataRole.UserRole:
            return item
        return None

    def flags(self, index):
        if index.isValid() and isinstance(self.items[index.row()], GroupTitle):
            return Qt.ItemFlag.NoItemFlags  # non selezionabile né cliccabile
        return super().flags(index)


class TileDelegate(QStyledItemDelegate):
    favorite_clicked = Signal(str)

    def __init__(self, logos, favorites_ref, parent=None):
        super().__init__(parent)
        self.logos = logos
        self.favorites_ref = favorites_ref  # funzione che ritorna l'insieme dei preferiti
        self.name_font = S.ui_font()
        self.name_font.setPixelSize(14)
        self.name_font.setWeight(QFont.Weight.DemiBold)
        self.small_font = S.ui_font()
        self.small_font.setPixelSize(11)
        self.small_font.setWeight(QFont.Weight.Bold)
        self.num_font = S.ui_font()
        self.num_font.setPixelSize(17)
        self.num_font.setWeight(QFont.Weight.Bold)

    def sizeHint(self, option, index):
        if isinstance(index.data(Qt.ItemDataRole.UserRole), GroupTitle):
            # larga quanto la griglia: va a capo da sola e occupa tutta la riga
            view = self.parent()
            width = view.viewport().width() - 2 if view is not None else TILE.width()
            return QSize(max(width, TILE.width()), GROUP_TITLE_H)
        return TILE

    def _paint_group(self, p, title, rect):
        p.save()
        bar = QRectF(rect.left() + 8, rect.bottom() - 26, 4, 18)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bp = QPainterPath()
        bp.addRoundedRect(bar, 2, 2)
        p.fillPath(bp, QColor(S.ACCENT))
        f = S.ui_font()
        f.setPixelSize(14)
        f.setWeight(QFont.Weight.ExtraBold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1)
        p.setFont(f)
        text = title.label.upper()
        x = bar.right() + 10
        text_rect = QRectF(x, bar.top() - 3, rect.width(), 24)
        p.setPen(QColor(S.GRAY300))
        p.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        p.setPen(QColor(S.GRAY500))
        w = QFontMetrics(f).horizontalAdvance(text)
        p.drawText(text_rect.translated(w + 8, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   str(title.count))
        p.restore()

    @staticmethod
    def card_rect(option_rect):
        return QRectF(option_rect).adjusted(6, 6, -6, -6)

    def star_rect(self, option_rect):
        r = self.card_rect(option_rect)
        return QRectF(r.right() - 34, r.top() + 6, 28, 28)

    def paint(self, p, option, index):
        item = index.data(Qt.ItemDataRole.UserRole)
        if isinstance(item, GroupTitle):
            self._paint_group(p, item, option.rect)
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.card_rect(option.rect)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        p.fillPath(path, QColor("#243349") if hover else QColor(S.NAVY2))
        if selected or hover:
            p.setPen(QPen(QColor(S.ACCENT), 2))
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 13, 13)

        logo = QRectF(r.center().x() - 36, r.top() + 16, 72, 72)
        if isinstance(item, AppStreaming):
            self._paint_app(p, item, logo)
        else:
            self._paint_channel(p, item, logo, hover, self.star_rect(option.rect))

        # nome
        p.setFont(self.name_font)
        p.setPen(QColor(S.WHITE))
        fm = QFontMetrics(self.name_font)
        name = item.nome if isinstance(item, AppStreaming) else item.name
        text_rect = QRectF(r.left() + 10, logo.bottom() + 10, r.width() - 20, 20)
        p.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(name, Qt.TextElideMode.ElideRight, int(text_rect.width())))

        # sotto il nome: numero canale oppure «Apri nel browser»
        p.setFont(self.small_font)
        sub = "APRI NEL BROWSER" if isinstance(item, AppStreaming) else f"CH {item.number}"
        sfm = QFontMetrics(self.small_font)
        w = sfm.horizontalAdvance(sub) + 16
        pill = QRectF(r.center().x() - w / 2, text_rect.bottom() + 4, w, 18)
        pp = QPainterPath()
        pp.addRoundedRect(pill, 9, 9)
        p.fillPath(pp, QColor(S.NAVY3))
        p.setPen(QColor(S.GRAY300))
        p.drawText(pill, Qt.AlignmentFlag.AlignCenter, sub)
        p.restore()

    def _paint_channel(self, p, ch, logo, hover, star):
        box = QPainterPath()
        box.addRoundedRect(logo, 12, 12)
        p.fillPath(box, QColor(S.NAVY3))
        pm = self.logos.get(ch.logo)
        if pm is not None and not pm.isNull():
            inner = logo.adjusted(7, 7, -7, -7)
            size = pm.size().scaled(inner.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRect(0, 0, size.width(), size.height())
            target.moveCenter(inner.center().toPoint())
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawPixmap(target, pm)
        else:
            p.setFont(self.num_font)
            p.setPen(QColor(S.GRAY300))
            p.drawText(logo, Qt.AlignmentFlag.AlignCenter, str(ch.number))
        fav = ch.name in self.favorites_ref()
        if fav or hover:
            p.setFont(S.icon_font(16))
            p.setPen(QColor(S.ACCENT) if fav else QColor(S.GRAY500))
            p.drawText(star, Qt.AlignmentFlag.AlignCenter, S.ICO_STAR_FILL if fav else S.ICO_STAR)

    def _paint_app(self, p, app, logo):
        box = QPainterPath()
        box.addRoundedRect(logo, 16, 16)
        pm = self.logos.get(app.logo)
        if pm is not None and not pm.isNull():
            # logo ufficiale a tutto riquadro; quelli trasparenti (es. la N di Netflix) su fondo navy
            p.fillPath(box, QColor(S.NAVY3))
            p.save()
            p.setClipPath(box)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            size = pm.size().scaled(logo.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRect(0, 0, size.width(), size.height())
            target.moveCenter(logo.center().toPoint())
            p.drawPixmap(target, pm)
            p.restore()
            return
        p.fillPath(box, QColor(app.colore))
        f = S.ui_font()
        f.setWeight(QFont.Weight.Black)
        f.setPixelSize(26 if len(app.sigla) <= 2 else 18)
        p.setFont(f)
        light = QColor(app.colore).lightness() > 170
        p.setPen(QColor("#111111") if light else QColor(S.WHITE))
        p.drawText(logo, Qt.AlignmentFlag.AlignCenter, app.sigla)

    def editorEvent(self, event, model, option, index):
        item = index.data(Qt.ItemDataRole.UserRole)
        if isinstance(item, Channel) and event.type() == QEvent.Type.MouseButtonRelease \
                and event.button() == Qt.MouseButton.LeftButton \
                and self.star_rect(option.rect).contains(event.position()):
            self.favorite_clicked.emit(item.name)
            return True
        return super().editorEvent(event, model, option, index)


class TileView(QListView):
    activated_item = Signal(object)
    context_item = Signal(object, object)  # item, posizione globale

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("grid")
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        # niente griglia fissa né misure uniformi: i titoli di gruppo sono larghi quanto la riga
        self.setUniformItemSizes(False)
        self.setSpacing(0)
        self.setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(24)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setWordWrap(False)
        self.setLayoutMode(QListView.LayoutMode.Batched)
        self.setBatchSize(300)
        self.clicked.connect(self._clicked)
        self.customContextMenuRequested.connect(self._menu)

    def _clicked(self, index):
        # il clic sulla stella è gestito dal delegato: qui arriva solo il resto della tessera
        item = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(item, GroupTitle):
            self.activated_item.emit(item)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if e.size().width() != e.oldSize().width():
            self.scheduleDelayedItemsLayout()  # i titoli di gruppo seguono la nuova larghezza

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and self.currentIndex().isValid():
            item = self.currentIndex().data(Qt.ItemDataRole.UserRole)
            if not isinstance(item, GroupTitle):
                self.activated_item.emit(item)
            return
        before = self.currentIndex()
        super().keyPressEvent(e)
        # le frecce non si fermano sui titoli di gruppo: si ripete il tasto fino alla prima tessera
        for _ in range(3):
            if not isinstance(self.currentIndex().data(Qt.ItemDataRole.UserRole), GroupTitle):
                break
            super().keyPressEvent(e)
        if isinstance(self.currentIndex().data(Qt.ItemDataRole.UserRole), GroupTitle) and before.isValid():
            self.setCurrentIndex(before)

    def _menu(self, pos):
        index = self.indexAt(pos)
        if index.isValid():
            self.context_item.emit(index.data(Qt.ItemDataRole.UserRole), self.viewport().mapToGlobal(pos))


# ---------------------------------------------------------------- barra laterale
ROLE_COUNT = Qt.ItemDataRole.UserRole + 1
ROLE_ICON = Qt.ItemDataRole.UserRole + 2


def section_icon(key, label):
    fixed = {"tutti": S.ICO_LIST, "generalisti": S.ICO_TV, "preferiti": S.ICO_STAR_FILL, "app": S.ICO_GLOBE}
    if key in fixed:
        return fixed[key]
    name = label.lower()
    for words, glyph in ((("radio", "musica", "music"), S.ICO_RADIO),
                         (("bambin", "kids", "ragazzi", "cartoni"), S.ICO_KIDS),
                         (("notizie", "news", "informazione"), S.ICO_NEWS),
                         (("document", "sport", "cultura", "scienz"), S.ICO_DOCS),
                         (("intratten", "film", "cinema", "serie"), S.ICO_MOVIE),
                         (("relig", "fede"), S.ICO_HEART)):
        if any(w in name for w in words):
            return glyph
    return S.ICO_TV


class SidebarDelegate(QStyledItemDelegate):
    """Voci della barra laterale: icona in un riquadro, nome e numero di canali in una pillola."""

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 38 if index.data(Qt.ItemDataRole.UserRole) is None else 50)

    def paint(self, p, option, index):
        key = index.data(Qt.ItemDataRole.UserRole)
        r = QRectF(option.rect).adjusted(8, 3, -8, -3)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if key is None:  # titolo «Gruppi»
            f = S.ui_font()
            f.setPixelSize(11)
            f.setWeight(QFont.Weight.Bold)
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
            p.setFont(f)
            p.setPen(QColor(S.GRAY500))
            text = index.data(Qt.ItemDataRole.DisplayRole).upper()
            tr = QRectF(r.left() + 12, r.bottom() - 18, r.width(), 16)
            p.drawText(tr, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
            x = tr.left() + QFontMetrics(f).horizontalAdvance(text) + 12
            p.setPen(QPen(QColor(S.NAVY2), 1))
            p.drawLine(int(x), int(tr.center().y()), int(r.right() - 6), int(tr.center().y()))
            p.restore()
            return

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        box = QPainterPath()
        box.addRoundedRect(r, 12, 12)
        if selected:
            g = QLinearGradient(r.topLeft(), r.topRight())
            c1, c2 = QColor(S.ACCENT), QColor(S.ACCENT)
            c1.setAlphaF(0.30)
            c2.setAlphaF(0.04)
            g.setColorAt(0, c1)
            g.setColorAt(1, c2)
            p.fillPath(box, g)
            bar = QPainterPath()
            bar.addRoundedRect(QRectF(r.left(), r.top() + 10, 3.5, r.height() - 20), 1.75, 1.75)
            p.fillPath(bar, QColor(S.ACCENT))
        elif hover:
            p.fillPath(box, QColor(S.NAVY2))

        # icona
        tile = QRectF(r.left() + 12, r.center().y() - 16, 32, 32)
        tp = QPainterPath()
        tp.addRoundedRect(tile, 9, 9)
        if selected:
            tg = QLinearGradient(tile.topLeft(), tile.bottomRight())
            tg.setColorAt(0, QColor(S.ACCENT))
            tg.setColorAt(1, QColor(S.ACCENT_D))
            p.fillPath(tp, tg)
        else:
            p.fillPath(tp, QColor(S.NAVY3) if hover else QColor(S.NAVY2))
        p.setFont(S.icon_font(15))
        p.setPen(QColor(S.WHITE) if selected else QColor(S.GRAY300))
        p.drawText(tile, Qt.AlignmentFlag.AlignCenter, index.data(ROLE_ICON) or S.ICO_TV)

        # numero di canali
        count = str(index.data(ROLE_COUNT) or 0)
        pf = S.ui_font()
        pf.setPixelSize(12)
        pf.setWeight(QFont.Weight.Bold)
        pw = QFontMetrics(pf).horizontalAdvance(count) + 18
        pill = QRectF(r.right() - 10 - pw, r.center().y() - 11, pw, 22)
        pp = QPainterPath()
        pp.addRoundedRect(pill, 11, 11)
        p.fillPath(pp, QColor(255, 255, 255, 38) if selected else (QColor(S.NAVY3) if hover else QColor(S.NAVY2)))
        p.setFont(pf)
        p.setPen(QColor(S.WHITE) if selected else QColor(S.GRAY300))
        p.drawText(pill, Qt.AlignmentFlag.AlignCenter, count)

        # nome
        nf = S.ui_font()
        nf.setPixelSize(15)
        nf.setWeight(QFont.Weight.Bold if selected else QFont.Weight.DemiBold)
        p.setFont(nf)
        p.setPen(QColor(S.WHITE) if (selected or hover) else QColor(S.GRAY300))
        lr = QRectF(tile.right() + 12, r.top(), pill.left() - tile.right() - 20, r.height())
        p.drawText(lr, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(nf).elidedText(index.data(Qt.ItemDataRole.DisplayRole), Qt.TextElideMode.ElideRight,
                                               int(lr.width())))
        p.restore()


# ---------------------------------------------------------------- schermata
class ChannelsPage(QWidget):
    play = Signal(object, list)          # canale, lista in cui fare zapping
    open_app = Signal(object)            # AppStreaming
    toggle_favorite = Signal(str)
    reload_requested = Signal()
    settings_requested = Signal()
    info_requested = Signal()
    update_requested = Signal()

    def __init__(self, store, logos, parent=None):
        super().__init__(parent)
        self.store = store
        self.logos = logos
        self.channels = []      # canali della lista
        self.favorites = store.favorites
        self.section = "tutti"  # all'avvio sempre tutti i canali divisi per gruppo, come nell'app Android
        self.shown = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = Header(APP_TITLE, "")
        self.search = QLineEdit()
        self.search.setObjectName("searchBox")
        self.search.setPlaceholderText("Cerca canale…  (⌘F)" if sys.platform == "darwin" else "Cerca canale…  (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(300)
        self.header.row.addWidget(self.search)
        self.update_btn = QToolButton()
        self.update_btn.setObjectName("headerAction")
        self.update_btn.setText(S.ICO_UPDATE)
        self.update_btn.setFont(S.icon_font(16))
        self.update_btn.setStyleSheet(f"QToolButton#headerAction {{ background:{S.GREEN}; }}")
        self.update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_btn.hide()
        self.header.row.addWidget(self.update_btn)
        self.reload_btn = header_button(S.ICO_REFRESH, "Ricarica la playlist (F5)")
        self.settings_btn = header_button(S.ICO_SETTINGS, "Impostazioni")
        self.info_btn = header_button(S.ICO_INFO, "Informazioni")
        for b in (self.reload_btn, self.settings_btn, self.info_btn):
            self.header.row.addWidget(b)
        root.addWidget(self.header)

        self.notice = QLabel("")
        self.notice.setWordWrap(True)
        self.notice.setStyleSheet(f"background:{S.NAVY2}; color:{S.ACCENT_L}; padding:8px 22px;")
        self.notice.hide()
        root.addWidget(self.notice)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(270)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.sidebar.setMouseTracking(True)
        self.sidebar.setItemDelegate(SidebarDelegate(self.sidebar))
        body.addWidget(self.sidebar)

        right = QVBoxLayout()
        right.setContentsMargins(18, 14, 12, 0)
        right.setSpacing(6)
        title_row = QHBoxLayout()
        bar = QLabel()
        bar.setFixedSize(4, 18)
        bar.setStyleSheet(f"background:{S.ACCENT}; border-radius:2px;")
        self.section_title = QLabel("")
        self.section_title.setStyleSheet(f"color:{S.GRAY300}; font-size:14px; font-weight:800; letter-spacing:1px;")
        self.section_count = QLabel("")
        self.section_count.setStyleSheet(f"color:{S.GRAY500}; font-size:14px; font-weight:800;")
        self.section_hint = QLabel("")
        self.section_hint.setObjectName("muted")
        title_row.addWidget(bar)
        title_row.addSpacing(4)
        title_row.addWidget(self.section_title)
        title_row.addWidget(self.section_count)
        title_row.addStretch(1)
        title_row.addWidget(self.section_hint)
        right.addLayout(title_row)

        self.model = TileModel(self)
        self.view = TileView()
        self.delegate = TileDelegate(logos, lambda: self.favorites, self.view)
        self.view.setModel(self.model)
        self.view.setItemDelegate(self.delegate)
        right.addWidget(self.view, 1)
        self.empty = QLabel("Nessun canale trovato")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setObjectName("soft")
        self.empty.hide()
        right.addWidget(self.empty, 1)
        body.addLayout(right, 1)
        root.addLayout(body, 1)

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(180)
        self.search_timer.timeout.connect(self.refresh_grid)
        self.search.textChanged.connect(lambda _: self.search_timer.start())
        self.sidebar.currentItemChanged.connect(self._section_changed)
        self.view.activated_item.connect(self._activate)
        self.view.context_item.connect(self._context_menu)
        self.delegate.favorite_clicked.connect(self.toggle_favorite)
        self.reload_btn.clicked.connect(self.reload_requested)
        self.settings_btn.clicked.connect(self.settings_requested)
        self.info_btn.clicked.connect(self.info_requested)
        self.update_btn.clicked.connect(self.update_requested)
        logos.loaded.connect(lambda _url: self.view.viewport().update())

    # ------------------------------------------------------------ dati
    def set_channels(self, channels):
        self.channels = list(channels)
        self.header.subtitle.setText(f"{len(self.channels)} canali")
        self.rebuild_sidebar()

    def set_favorites(self, favs):
        self.favorites = set(favs)
        self.rebuild_sidebar()

    def set_notice(self, text):
        self.notice.setText(text)
        self.notice.setVisible(bool(text))

    def show_update(self, version):
        self.update_btn.setVisible(bool(version))
        if version:
            self.update_btn.setToolTip(f"È disponibile tk-tv {version}: clicca per aggiornare")

    def sections(self):
        groups = {}
        for c in self.channels:
            groups.setdefault(c.group or "Altri canali", []).append(c)
        # «Tutti i canali» in cima: è la schermata di partenza
        out = [("tutti", "Tutti i canali", self.channels), ("generalisti", "Generalisti", generalisti(self.channels))]
        favs = [c for c in self.channels if c.name in self.favorites]
        out.append(("preferiti", "Preferiti", favs))
        out.append(("app", "App e pay TV", CATALOGO))
        for g in sorted(groups, key=str.lower):
            out.append((f"g:{g}", g, groups[g]))
        return out

    def grouped_all(self):
        """«Tutti i canali» come nell'app Android: Generalisti, Preferiti e poi ogni gruppo, ciascuno col suo titolo."""
        out, titles = [], set()
        for key, label, items in self.sections():
            # un gruppo della playlist con lo stesso nome di una sezione già mostrata (es. «Generalisti») non si ripete
            if key in ("tutti", "app") or not items or label.lower() in titles:
                continue
            titles.add(label.lower())
            out.append(GroupTitle(label, len(items)))
            out.extend(items)
        return out

    def rebuild_sidebar(self):
        current = self.section
        self.sidebar.blockSignals(True)
        self.sidebar.clear()
        self._sections = {}
        target = None
        groups_started = False
        labels = set()
        for key, label, items in self.sections():
            if key == "preferiti" and not items:
                continue
            if key.startswith("g:") and label.lower() in labels:
                continue  # gruppo della playlist con lo stesso nome di una sezione (es. «Generalisti»)
            labels.add(label.lower())
            if key.startswith("g:") and not groups_started:
                groups_started = True
                sep = QListWidgetItem("Gruppi")
                sep.setFlags(Qt.ItemFlag.NoItemFlags)
                self.sidebar.addItem(sep)
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, key)
            it.setData(ROLE_COUNT, len(items))
            it.setData(ROLE_ICON, section_icon(key, label))
            it.setToolTip(f"{label} · {len(items)} canali")
            self.sidebar.addItem(it)
            self._sections[key] = (label, items)
            if key == current:
                target = it
        if target is None:
            target = next((self.sidebar.item(i) for i in range(self.sidebar.count())
                           if self.sidebar.item(i).data(Qt.ItemDataRole.UserRole)), None)
        self.sidebar.blockSignals(False)
        if target is not None:
            self.sidebar.setCurrentItem(target)
            self.section = target.data(Qt.ItemDataRole.UserRole)
        self.refresh_grid()

    def _section_changed(self, item, _prev):
        if item is None or not item.data(Qt.ItemDataRole.UserRole):
            return
        self.section = item.data(Qt.ItemDataRole.UserRole)
        self.store.last_section = self.section
        if self.search.text():
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
        self.refresh_grid()

    def refresh_grid(self):
        query = self.search.text().strip().lower()
        if query:
            chans = [c for c in self.channels if query in c.name.lower()]
            apps = [a for a in CATALOGO if query in a.nome.lower()]
            items = chans + apps
            self.section_title.setText(f"RISULTATI PER «{self.search.text().strip().upper()}»")
            self.section_hint.setText("Invio per guardare il primo")
        else:
            label, items = getattr(self, "_sections", {}).get(self.section, ("", []))
            count = len(items)
            if self.section == "tutti":
                items = self.grouped_all()
            self.section_title.setText(label.upper())
            hints = {"app": "Si aprono nel browser: servono i tuoi abbonamenti"}
            self.section_hint.setText(hints.get(self.section, "Clic destro sulla tessera per altre opzioni"))
        self.shown = items
        self.section_count.setText(str(count if not query else len(items)))
        self.model.set_items(items)
        self.view.setVisible(bool(items))
        self.empty.setVisible(not items)
        if items:
            first = next((i for i, it in enumerate(items) if not isinstance(it, GroupTitle)), 0)
            self.view.setCurrentIndex(self.model.index(first))
            self.view.scrollToTop()

    def zapping_list(self):
        # in «Tutti» un canale può comparire due volte (Generalisti/Preferiti e il suo gruppo): una sola nello zapping
        seen, out = set(), []
        for i in self.shown:
            if isinstance(i, Channel) and id(i) not in seen:
                seen.add(id(i))
                out.append(i)
        return out

    # ------------------------------------------------------------ azioni
    def _activate(self, item):
        if isinstance(item, AppStreaming):
            self.open_app.emit(item)
        elif isinstance(item, Channel):
            self.play.emit(item, self.zapping_list())

    def _context_menu(self, item, pos):
        if not isinstance(item, Channel):
            return
        menu = QMenu(self)
        menu.addAction("Guarda", lambda: self._activate(item))
        fav = item.name in self.favorites
        menu.addAction("Rimuovi dai preferiti" if fav else "Aggiungi ai preferiti",
                       lambda: self.toggle_favorite.emit(item.name))
        menu.exec(pos)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_F and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.search.setFocus()
            self.search.selectAll()
            return
        if e.key() == Qt.Key.Key_F5:
            self.reload_requested.emit()
            return
        super().keyPressEvent(e)

    def focus_grid(self):
        self.view.setFocus()
