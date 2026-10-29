"""Player: video libVLC incorporato + comandi in sovrimpressione che si nascondono da soli (come su Android).

Il video di VLC è una finestra nativa: i widget Qt non possono disegnarci sopra. I comandi stanno
quindi in una finestra trasparente «posseduta» dalla finestra principale, allineata all'area video,
che raccoglie anche mouse, doppio clic e rotellina.
"""
import ctypes
import subprocess
import sys
import threading
import time

from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QLinearGradient, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QToolButton, QVBoxLayout, QWidget

from tktv import engine
from tktv import style as S

CONTROLS_TIMEOUT_MS = 4000
CONNECT_TIMEOUT_MS = 25000
DIGIT_TIMEOUT_MS = 1500
SLEEP_STEPS = (0, 30, 60, 90, 120)  # minuti del timer di spegnimento (0 = spento), si passano col tasto T

ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x00000001, 0x00000002


_caffeinate = None
_inibizione = None  # Linux: (connessione D-Bus, indirizzo, metodo per togliere, cookie)
INIBITORI_LINUX = (
    # GNOME: 4 = niente sospensione, 8 = la sessione non diventa inattiva (niente salvaschermo né schermo spento)
    ("org.gnome.SessionManager", "/org/gnome/SessionManager", "org.gnome.SessionManager",
     "Inhibit", "susu", ("tk-tv", 0, "Riproduzione di un canale", 4 | 8), "Uninhibit"),
    # KDE, XFCE e gli altri desktop
    ("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver", "org.freedesktop.ScreenSaver",
     "Inhibit", "ss", ("tk-tv", "Riproduzione di un canale"), "UnInhibit"),
)


def _linux_keep_awake(on):
    """Linux: inibizione via D-Bus (jeepney), legata alla connessione: se tk-tv si chiude di colpo il desktop la
    toglie da solo. Si rilascia alla pausa, all'uscita dal canale e alla chiusura."""
    global _inibizione
    try:
        from jeepney import DBusAddress, new_method_call
        from jeepney.io.blocking import open_dbus_connection
        from jeepney.wrappers import unwrap_msg
    except ImportError:
        return
    if on and _inibizione is None:
        try:
            conn = open_dbus_connection(bus="SESSION")
        except Exception:
            return  # niente bus di sessione (per esempio nei test senza desktop)
        for dest, path, iface, metodo, firma, args, togli in INIBITORI_LINUX:
            try:
                addr = DBusAddress(path, bus_name=dest, interface=iface)
                cookie = unwrap_msg(conn.send_and_get_reply(new_method_call(addr, metodo, firma, args), timeout=3))[0]
                _inibizione = (conn, addr, togli, cookie)
                return
            except Exception:
                continue
        conn.close()
    elif not on and _inibizione is not None:
        conn, addr, togli, cookie = _inibizione
        _inibizione = None
        try:
            conn.send_and_get_reply(new_method_call(addr, togli, "u", (cookie,)), timeout=3)
        except Exception:
            pass
        conn.close()


def screen_kept_on():
    """Per il selftest: True se su Linux l'inibizione del salvaschermo è attiva."""
    return _inibizione is not None


def keep_screen_on(on):
    """Durante la riproduzione niente salvaschermo né sospensione del PC."""
    global _caffeinate
    if sys.platform.startswith("linux"):
        _linux_keep_awake(on)
        return
    if sys.platform == "darwin":
        # caffeinate di sistema: -d schermo acceso, -i niente stop; -w termina con tk-tv anche se si chiude di colpo
        import os
        if on and (_caffeinate is None or _caffeinate.poll() is not None):
            try:
                _caffeinate = subprocess.Popen(["/usr/bin/caffeinate", "-d", "-i", "-w", str(os.getpid())])
            except OSError:
                _caffeinate = None
        elif not on and _caffeinate is not None:
            _caffeinate.terminate()
            _caffeinate = None
        return
    try:
        flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED if on else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
    except Exception:
        pass


def unblocked(fn, *args):
    """Su Mac stop e cambio flusso di libVLC aspettano la chiusura del video, che avviene sul thread
    principale: chiamati da lì lo bloccano per sempre. Si eseguono in un thread mentre il thread
    principale continua a gestire gli eventi (compresi quelli che servono a VLC)."""
    if sys.platform != "darwin":
        return fn(*args)
    done = threading.Event()
    result = []

    def work():
        try:
            result.append(fn(*args))
        finally:
            done.set()

    threading.Thread(target=work, daemon=True).start()
    while not done.wait(0.005):
        QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 10)
    return result[0] if result else None


def _button(glyph, tip, size=18, big=False):
    b = QToolButton()
    b.setText(glyph)
    b.setFont(S.icon_font(size))
    b.setToolTip(tip)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    d = 52 if big else 40
    b.setFixedSize(d, d)
    b.setStyleSheet(_button_css(big))
    return b


def _button_css(big=False, color="white"):
    d = 52 if big else 40
    return (f"QToolButton {{ background: {'rgba(255,255,255,0.14)' if big else 'transparent'}; color: {color};"
            f" border: 0; border-radius: {d // 2}px; }}"
            f"QToolButton:hover {{ background: {S.ACCENT}; color: white; }}"
            f"QToolButton:disabled {{ color: rgba(255,255,255,0.3); background: transparent; }}")


class VlcEvents(QObject):
    """Porta gli eventi di libVLC (thread di VLC) nel thread dell'interfaccia."""
    playing = Signal()
    vout = Signal()
    error = Signal()
    ended = Signal()
    buffering = Signal(float)


class Overlay(QWidget):
    """Finestra trasparente sopra il video: barre dei comandi, messaggi e raccolta degli input del mouse."""

    def __init__(self, page):
        super().__init__(page.window(), Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.NoDropShadowWindowHint)
        self.page = page
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.controls_visible = True

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # --- barra superiore: indietro, nome canale, stella, aggiorna
        self.top = QWidget()
        self.top.setMouseTracking(True)
        t = QHBoxLayout(self.top)
        t.setContentsMargins(14, 12, 14, 26)
        self.back_btn = _button(S.ICO_BACK, "Torna ai canali (Esc)")
        t.addWidget(self.back_btn)
        t.addSpacing(6)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = QLabel("")
        self.title.setStyleSheet("color:white; font-size:20px; font-weight:800; background:transparent;")
        self.subtitle = QLabel("")
        self.subtitle.setStyleSheet(f"color:{S.GRAY300}; font-size:14px; background:transparent;")
        col.addWidget(self.title)
        col.addWidget(self.subtitle)
        t.addLayout(col, 1)
        self.fav_btn = _button(S.ICO_STAR, "Aggiungi ai preferiti")
        self.reload_btn = _button(S.ICO_REFRESH, "Aggiorna il flusso (R)")
        t.addWidget(self.fav_btn)
        t.addWidget(self.reload_btn)
        lay.addWidget(self.top)

        # --- centro: messaggi (caricamento, errore) e numero digitato
        mid = QHBoxLayout()
        mid.setContentsMargins(20, 0, 20, 0)
        mid.addStretch(1)
        self.message = QLabel("")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setStyleSheet("color:white; font-size:17px; font-weight:600; background:rgba(15,23,42,0.82);"
                                   "border-radius:12px; padding:14px 22px;")
        self.message.hide()
        mid.addWidget(self.message, 0, Qt.AlignmentFlag.AlignCenter)
        mid.addStretch(1)
        lay.addStretch(1)
        lay.addLayout(mid)
        lay.addStretch(1)

        self.digits = QLabel("", self)
        self.digits.setStyleSheet(f"color:white; font-size:44px; font-weight:800; background:rgba(15,23,42,0.85);"
                                  f"border:2px solid {S.ACCENT}; border-radius:14px; padding:6px 20px;")
        self.digits.hide()

        # avviso discreto in basso (es. «tk-tv si spegne tra 1 minuto»): non copre il video come il messaggio centrale
        self.banner = QLabel("", self)
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setStyleSheet(f"color:white; font-size:15px; font-weight:600; background:rgba(15,23,42,0.82);"
                                  f"border-left:4px solid {S.ACCENT}; border-radius:10px; padding:9px 18px;")
        self.banner.hide()

        # --- barra inferiore: zapping, pausa, volume, schermo intero
        self.bottom = QWidget()
        self.bottom.setMouseTracking(True)
        b = QHBoxLayout(self.bottom)
        b.setContentsMargins(18, 26, 18, 16)
        b.setSpacing(10)
        self.vol_btn = _button(S.ICO_VOLUME, "Disattiva audio (M)")
        self.vol = QSlider(Qt.Orientation.Horizontal)
        self.vol.setRange(0, 125)
        self.vol.setFixedWidth(130)
        self.vol.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.vol.setToolTip("Volume (rotellina del mouse)")
        b.addWidget(self.vol_btn)
        b.addWidget(self.vol)
        b.addStretch(1)
        self.prev_btn = _button(S.ICO_PREV, "Canale precedente (↑ / PagSu)", 18, True)
        self.pause_btn = _button(S.ICO_PAUSE, "Pausa (Spazio)", 18, True)
        self.next_btn = _button(S.ICO_NEXT, "Canale successivo (↓ / PagGiù)", 18, True)
        b.addWidget(self.prev_btn)
        b.addSpacing(8)
        b.addWidget(self.pause_btn)
        b.addSpacing(8)
        b.addWidget(self.next_btn)
        b.addStretch(1)
        self.hint = QLabel("Digita il numero per cambiare canale")
        self.hint.setStyleSheet(f"color:{S.GRAY300}; font-size:13px; background:transparent;")
        b.addWidget(self.hint)
        self.lang_btn = _button(S.ICO_LANG, "Lingua dell'audio (A)")
        self.sleep_btn = _button(S.ICO_TIMER, "Timer di spegnimento (T)")
        b.addWidget(self.lang_btn)
        b.addWidget(self.sleep_btn)
        self.full_btn = _button(S.ICO_FULL, "Schermo intero (F / doppio clic)")
        b.addWidget(self.full_btn)
        lay.addWidget(self.bottom)

    def set_controls_visible(self, on):
        self.controls_visible = on
        self.top.setVisible(on)
        self.bottom.setVisible(on)
        # l'avviso segue i comandi: informa senza restare fisso sopra il video
        self.banner.setVisible(on and bool(self.banner.text()))
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        # alfa minimo ma non nullo: la finestra resta «piena» e riceve i clic anche sopra il video
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))
        if self.controls_visible:
            g = QLinearGradient(0, 0, 0, self.top.height())
            g.setColorAt(0, QColor(0, 0, 0, 190))
            g.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillRect(QRect(0, 0, self.width(), self.top.height()), g)
            y = self.height() - self.bottom.height()
            g = QLinearGradient(0, y, 0, self.height())
            g.setColorAt(0, QColor(0, 0, 0, 0))
            g.setColorAt(1, QColor(0, 0, 0, 200))
            p.fillRect(QRect(0, y, self.width(), self.bottom.height()), g)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.place_digits()
        self.place_banner()

    def place_digits(self):
        self.digits.adjustSize()
        self.digits.move(self.width() - self.digits.width() - 30, 90)

    def set_banner(self, text):
        self.banner.setText(text)
        self.banner.setVisible(bool(text) and self.controls_visible)
        self.place_banner()

    def place_banner(self):
        self.banner.adjustSize()
        self.banner.move((self.width() - self.banner.width()) // 2, self.height() - self.banner.height() - 110)

    # gli input del mouse arrivano qui e vanno alla pagina
    def mouseMoveEvent(self, e):
        self.page.user_activity()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.page.click_timer.start()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.page.click_timer.stop()
            self.page.fullscreen_toggled.emit()

    def wheelEvent(self, e):
        step = 5 if e.angleDelta().y() > 0 else -5
        self.page.change_volume(step)

    def keyPressEvent(self, e):
        self.page.keyPressEvent(e)


class PlayerPage(QWidget):
    back = Signal()
    fullscreen_toggled = Signal()
    toggle_favorite = Signal(str)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet("background:black;")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.video = QWidget()
        self.video.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.video.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self.video.setStyleSheet("background:black;")
        self.video.setAutoFillBackground(True)
        lay.addWidget(self.video)

        self.channels = []
        self.index = 0
        self.lookup = None       # funzione numero -> (canale, lista) per il numero digitato
        self.favorites = set()
        self.is_fullscreen = False
        self.mp = None
        self.events = VlcEvents(self)
        self._callbacks = []
        self._last_cursor = QPoint()
        self._digit_buffer = ""
        self._retried = False
        self._muted_volume = None

        self.overlay = None
        self.hide_timer = QTimer(self, singleShot=True, interval=CONTROLS_TIMEOUT_MS, timeout=self._auto_hide)
        self.connect_timer = QTimer(self, singleShot=True, interval=CONNECT_TIMEOUT_MS, timeout=self._timeout)
        self.digit_timer = QTimer(self, singleShot=True, interval=DIGIT_TIMEOUT_MS, timeout=self._digits_done)
        self.click_timer = QTimer(self, singleShot=True, timeout=self._single_click)
        self.sync_timer = QTimer(self, interval=250, timeout=self._sync)
        # timer di spegnimento: resta attivo anche tornando alla lista dei canali
        self.sleep_minutes = 0
        self._sleep_end = 0
        self.sleep_timer = QTimer(self, singleShot=True, timeout=self._sleep_now)
        self.sleep_warn = QTimer(self, singleShot=True, timeout=self._sleep_warning)

        self.events.playing.connect(self._on_playing)
        self.events.vout.connect(self._on_vout)
        # canali solo audio (radio): nessuna immagine arriverà, si toglie il messaggio poco dopo
        self.audio_timer = QTimer(self, singleShot=True, interval=4000, timeout=self._on_vout)
        self.events.error.connect(self._on_error)
        self.events.ended.connect(self._on_ended)
        self.events.buffering.connect(self._on_buffering)

    # ------------------------------------------------------------ motore
    def _ensure_player(self):
        if self.mp is not None:
            return
        inst = engine.instance()
        vlc = engine.load()
        self.mp = inst.media_player_new()
        if sys.platform == "darwin":
            self.mp.set_nsobject(int(self.video.winId()))  # winId su Mac = NSView
        elif sys.platform.startswith("linux"):
            # finestra X11 (tk-tv gira con XWayland, vedi util.prepare_linux_display); senza X11 (test senza
            # schermo) il video va dove dice l'istanza (--vout=dummy nel selftest)
            from PySide6.QtGui import QGuiApplication
            if QGuiApplication.platformName() == "xcb":
                self.mp.set_xwindow(int(self.video.winId()))
        else:
            self.mp.set_hwnd(int(self.video.winId()))
        self.mp.video_set_mouse_input(False)
        self.mp.video_set_key_input(False)
        em = self.mp.event_manager()
        for etype, sig in ((vlc.EventType.MediaPlayerPlaying, self.events.playing),
                           (vlc.EventType.MediaPlayerVout, self.events.vout),
                           (vlc.EventType.MediaPlayerEncounteredError, self.events.error),
                           (vlc.EventType.MediaPlayerEndReached, self.events.ended)):
            cb = (lambda s: (lambda _ev: s.emit()))(sig)
            self._callbacks.append(cb)
            em.event_attach(etype, cb)
        cb = lambda ev: self.events.buffering.emit(float(ev.u.new_cache))
        self._callbacks.append(cb)
        em.event_attach(vlc.EventType.MediaPlayerBuffering, cb)

    def _ensure_overlay(self):
        if self.overlay is not None:
            return
        o = self.overlay = Overlay(self)
        o.back_btn.clicked.connect(self.back)
        o.reload_btn.clicked.connect(self.reload)
        o.prev_btn.clicked.connect(self.previous)
        o.next_btn.clicked.connect(self.next)
        o.pause_btn.clicked.connect(self.toggle_pause)
        o.full_btn.clicked.connect(self.fullscreen_toggled)
        o.vol_btn.clicked.connect(self.toggle_mute)
        o.vol.valueChanged.connect(self._volume_changed)
        o.fav_btn.clicked.connect(self._fav_clicked)
        o.lang_btn.clicked.connect(self.cycle_audio)
        o.sleep_btn.clicked.connect(self.cycle_sleep)
        o.vol.setValue(self.store.volume)
        self._sleep_look()

    # ------------------------------------------------------------ API
    def start(self, channels, index):
        self.channels = list(channels)
        self.index = max(0, min(index, len(self.channels) - 1))
        self._ensure_overlay()
        self.play_current()

    def stop(self):
        if self.overlay is not None:
            self.overlay.set_banner("")
        self.connect_timer.stop()
        self.audio_timer.stop()
        self.hide_timer.stop()
        self.sync_timer.stop()
        if self.overlay is not None:
            self.overlay.hide()
        if self.mp is not None:
            unblocked(self.mp.stop)
        keep_screen_on(False)

    def current(self):
        return self.channels[self.index] if self.channels else None

    def play_current(self):
        ch = self.current()
        if ch is None:
            return
        try:
            self._ensure_player()
            media, _vlc = engine.make_media(ch)
        except Exception as exc:
            self._show_message(str(exc))
            return
        self._retried = False
        self.store.last_channel = ch.name  # per «Riparti dall'ultimo canale»
        self.overlay.set_banner("")
        self.audio_timer.stop()
        unblocked(self.mp.set_media, media)
        media.release()
        self.mp.play()
        self.mp.audio_set_volume(self.overlay.vol.value())
        self.overlay.pause_btn.setText(S.ICO_PAUSE)
        self._update_title()
        self._show_message("Caricamento…")
        self.connect_timer.start()
        self.show_controls()
        keep_screen_on(True)

    def reload(self):
        self.play_current()

    def previous(self):
        if self.index > 0:
            self.index -= 1
            self.play_current()

    def next(self):
        if self.index < len(self.channels) - 1:
            self.index += 1
            self.play_current()

    def jump_to(self, channel, channels):
        self.channels = list(channels)
        self.index = self.channels.index(channel)
        self.play_current()

    def toggle_pause(self):
        if self.mp is None:
            return
        playing = self.mp.is_playing()
        self.mp.set_pause(1 if playing else 0)
        self.overlay.pause_btn.setText(S.ICO_PLAY if playing else S.ICO_PAUSE)
        self.overlay.pause_btn.setToolTip("Riprendi (Spazio)" if playing else "Pausa (Spazio)")
        keep_screen_on(not playing)
        self.show_controls()

    def change_volume(self, step):
        o = self.overlay
        o.vol.setValue(max(0, min(125, o.vol.value() + step)))
        self._show_toast(f"Volume {o.vol.value()}%")
        self.show_controls()

    def toggle_mute(self):
        o = self.overlay
        if o.vol.value() > 0:
            self._muted_volume = o.vol.value()
            o.vol.setValue(0)
        else:
            o.vol.setValue(self._muted_volume or 80)
        self.show_controls()

    def set_favorites(self, favs):
        self.favorites = set(favs)
        self._update_title()

    def set_fullscreen(self, on):
        self.is_fullscreen = on
        if self.overlay is not None:
            self.overlay.full_btn.setText(S.ICO_UNFULL if on else S.ICO_FULL)
            self.overlay.full_btn.setToolTip("Esci da schermo intero (F / Esc)" if on
                                             else "Schermo intero (F / doppio clic)")
        QTimer.singleShot(50, self._sync)
        QTimer.singleShot(300, self._sync)

    # ------------------------------------------------------------ comandi a schermo
    def show_controls(self):
        if self.overlay is None:
            return
        self.overlay.set_controls_visible(True)
        self.hide_timer.start()

    def _auto_hide(self):
        if self.overlay is not None:
            self.overlay.set_controls_visible(False)

    def user_activity(self):
        if self.overlay is not None and not self.overlay.controls_visible:
            self.show_controls()
        else:
            self.hide_timer.start()

    def _single_click(self):
        if self.overlay.controls_visible:
            self._auto_hide()
        else:
            self.show_controls()

    def _update_title(self):
        ch = self.current()
        if ch is None or self.overlay is None:
            return
        o = self.overlay
        o.title.setText(f"[{ch.number}] {ch.name}")
        pos = f"{self.index + 1} di {len(self.channels)}"
        o.subtitle.setText(f"{ch.group} · {pos}" if ch.group else pos)
        fav = ch.name in self.favorites
        o.fav_btn.setText(S.ICO_STAR_FILL if fav else S.ICO_STAR)
        o.fav_btn.setStyleSheet(_button_css(False, S.ACCENT if fav else "white"))
        o.fav_btn.setToolTip("Rimuovi dai preferiti" if fav else "Aggiungi ai preferiti")
        o.prev_btn.setEnabled(self.index > 0)
        o.next_btn.setEnabled(self.index < len(self.channels) - 1)

    def _fav_clicked(self):
        ch = self.current()
        if ch is not None:
            self.toggle_favorite.emit(ch.name)

    def _volume_changed(self, v):
        if self.mp is not None:
            self.mp.audio_set_volume(v)
        self.store.volume = v
        self.overlay.vol_btn.setText(S.ICO_MUTE if v == 0 else S.ICO_VOLUME)

    def _show_message(self, text):
        m = self.overlay.message if self.overlay else None
        if m is None:
            return
        m.setText(text)
        m.setVisible(bool(text))

    def _show_toast(self, text, ms=900):
        self._show_message(text)
        QTimer.singleShot(ms, lambda: self._show_message("") if self.overlay.message.text() == text else None)

    # ------------------------------------------------------------ timer di spegnimento e lingua dell'audio
    def cycle_sleep(self):
        nxt = SLEEP_STEPS[(SLEEP_STEPS.index(self.sleep_minutes) + 1) % len(SLEEP_STEPS)] \
            if self.sleep_minutes in SLEEP_STEPS else 0
        self.sleep_minutes = nxt
        self.sleep_timer.stop()
        self.sleep_warn.stop()
        if self.overlay is not None and self.overlay.banner.text().startswith("tk-tv si spegne"):
            self.overlay.set_banner("")
        if nxt:
            self.sleep_timer.start(nxt * 60000)
            self.sleep_warn.start((nxt - 1) * 60000)
            self._sleep_end = time.time() + nxt * 60
            self._show_toast(f"tk-tv si spegne tra {nxt} minuti\nT per cambiare", 2000)
        else:
            self._show_toast("Timer di spegnimento tolto", 1500)
        self._sleep_look()
        self.show_controls()

    def _sleep_look(self):
        if self.overlay is None:
            return
        on = self.sleep_minutes > 0
        self.overlay.sleep_btn.setStyleSheet(_button_css(False, S.ACCENT if on else "white"))
        self.overlay.sleep_btn.setToolTip(
            f"Si spegne alle {time.strftime('%H:%M', time.localtime(self._sleep_end))} · T per cambiare" if on
            else "Timer di spegnimento (T)")

    def _sleep_warning(self):
        if self.overlay is not None and self.isVisible():
            self.overlay.set_banner("tk-tv si spegne tra 1 minuto · premi T per rimandare")
            self.show_controls()

    def _sleep_now(self):
        self.sleep_minutes = 0
        self.window().close()

    def cycle_audio(self):
        if self.mp is None:
            return
        try:
            tracks = []
            for tid, name in self.mp.audio_get_track_description() or []:
                if tid >= 0:
                    tracks.append((tid, name.decode("utf-8", "replace") if isinstance(name, bytes) else str(name)))
        except Exception:
            tracks = []
        if len(tracks) < 2:
            self._show_toast("Questo canale ha una sola lingua", 1600)
            return
        ids = [t[0] for t in tracks]
        cur = self.mp.audio_get_track()
        k = (ids.index(cur) + 1) % len(ids) if cur in ids else 0
        self.mp.audio_set_track(ids[k])
        self._show_toast(f"Audio: {tracks[k][1]}", 1600)
        self.show_controls()

    # ------------------------------------------------------------ eventi VLC
    def _on_playing(self):
        self.connect_timer.stop()
        self.audio_timer.start()
        if self.mp is not None:
            self.mp.audio_set_volume(self.overlay.vol.value())

    def _on_vout(self):
        self.audio_timer.stop()
        if self.overlay is not None and self.overlay.message.text().startswith("Caricamento"):
            self._show_message("")

    def _on_buffering(self, pct):
        if self.overlay is not None and self.overlay.message.text().startswith("Caricamento"):
            if pct < 100:
                self._show_message(f"Caricamento… {int(pct)}%")

    def _fail(self, text):
        self._show_message(text)

    def _on_error(self):
        self.connect_timer.stop()
        self._fail("Questo canale non è raggiungibile\nPremi R per riprovare oppure cambia canale")

    def _on_ended(self):
        # una diretta non «finisce»: di solito è il flusso che si è interrotto. Un tentativo automatico.
        if not self._retried:
            self._retried = True
            QTimer.singleShot(1500, self._retry)
        else:
            self._fail("La trasmissione si è interrotta\nPremi R per riprovare")

    def _retry(self):
        if self.isVisible():
            self.play_current()
            self._retried = True  # play_current lo azzera: un solo tentativo automatico

    def _timeout(self):
        if engine.warming():
            # il sistema sta ancora controllando i plugin di VLC (Mac al primo avvio, Windows dopo un riavvio)
            self._show_message("Caricamento… preparo il motore video")
            self.connect_timer.start()
            return
        self._fail("Il canale non risponde\nPremi R per riprovare oppure cambia canale")

    # ------------------------------------------------------------ numero canale digitato
    def _digit(self, d):
        self._digit_buffer = (self._digit_buffer + d)[-4:]
        o = self.overlay
        o.digits.setText(self._digit_buffer)
        o.place_digits()
        o.digits.show()
        o.digits.raise_()
        self.digit_timer.start()

    def _digits_done(self):
        number = int(self._digit_buffer or 0)
        self._digit_buffer = ""
        self.overlay.digits.hide()
        found = self.lookup(number) if self.lookup else None
        if found:
            self.jump_to(*found)
        else:
            self._show_toast(f"Nessun canale {number}")

    # ------------------------------------------------------------ tastiera
    def keyPressEvent(self, e):
        k = e.key()
        if Qt.Key.Key_0 <= k <= Qt.Key.Key_9:
            self._digit(chr(k))
        elif k in (Qt.Key.Key_Up, Qt.Key.Key_PageUp, Qt.Key.Key_MediaPrevious, Qt.Key.Key_Left):
            self.previous()
        elif k in (Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_MediaNext, Qt.Key.Key_Right):
            self.next()
        elif k in (Qt.Key.Key_Space, Qt.Key.Key_MediaPlay, Qt.Key.Key_MediaTogglePlayPause, Qt.Key.Key_MediaPause):
            self.toggle_pause()
        elif k in (Qt.Key.Key_F, Qt.Key.Key_F11):
            self.fullscreen_toggled.emit()
        elif k == Qt.Key.Key_Escape:
            if self.is_fullscreen:
                self.fullscreen_toggled.emit()
            else:
                self.back.emit()
        elif k in (Qt.Key.Key_Backspace, Qt.Key.Key_Back):
            self.back.emit()
        elif k in (Qt.Key.Key_R, Qt.Key.Key_F5):
            self.reload()
        elif k == Qt.Key.Key_M or k == Qt.Key.Key_VolumeMute:
            self.toggle_mute()
        elif k in (Qt.Key.Key_Plus, Qt.Key.Key_VolumeUp):
            self.change_volume(5)
        elif k in (Qt.Key.Key_Minus, Qt.Key.Key_VolumeDown):
            self.change_volume(-5)
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_I):
            self._single_click()
        elif k == Qt.Key.Key_P:
            self._fav_clicked()
        elif k == Qt.Key.Key_T:
            self.cycle_sleep()
        elif k == Qt.Key.Key_A:
            self.cycle_audio()
        else:
            super().keyPressEvent(e)
            return
        if k not in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_I) and not (Qt.Key.Key_0 <= k <= Qt.Key.Key_9):
            self.user_activity()

    # ------------------------------------------------------------ allineamento della sovrimpressione
    def _sync(self):
        o = self.overlay
        if o is None:
            return
        win = self.window()
        visible = self.isVisible() and win.isVisible() and not win.isMinimized()
        if not visible:
            if o.isVisible():
                o.hide()
            return
        rect = QRect(self.video.mapToGlobal(QPoint(0, 0)), self.video.size())
        if o.geometry() != rect:
            o.setGeometry(rect)
        if not o.isVisible():
            o.show()
        # movimento del mouse sopra il video (anche se un'altra finestra ha il focus)
        pos = QCursor.pos()
        if pos != self._last_cursor:
            self._last_cursor = pos
            if rect.contains(pos) and win.isActiveWindow():
                self.user_activity()

    def showEvent(self, e):
        super().showEvent(e)
        self.sync_timer.start()
        QTimer.singleShot(0, self._sync)
        self.setFocus()

    def hideEvent(self, e):
        super().hideEvent(e)
        if self.overlay is not None:
            self.overlay.hide()
