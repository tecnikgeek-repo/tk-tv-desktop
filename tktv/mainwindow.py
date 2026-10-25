"""Finestra principale: collega lista canali, player, impostazioni e informazioni."""
import sys
import threading

from PySide6.QtCore import QByteArray, QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMainWindow, QStackedWidget

from tktv import APP_TITLE
from tktv import playlist
from tktv.channels import ChannelsPage
from tktv.logos import LogoLoader
from tktv.pages import InfoPage, SettingsPage
from tktv.player import PlayerPage
from tktv.store import Store
from tktv.updater_ui import UpdateManager


class _Loader(QObject):
    done = Signal(int, object, str)  # generazione, (testo, canali) oppure None, errore


class MainWindow(QMainWindow):
    def show_info(self):
        """Informazioni: finestra comune a tutti i software TK (libreria), colore di tk-tv. La pagina con le
        scorciatoie resta raggiungibile da «Tastiera e mouse»."""
        self._informazioni().exec()

    def _informazioni(self):
        from tktv import VERSION, URL_SORGENTE, pro
        from tktv.icon import badge_pixmap
        from tktv.tk_licenza_qt import InformazioniDialog
        from tktv.util import app_data_dir
        try:
            from tktv import engine
            vlc = "VLC " + engine.load().libvlc_get_version().decode().split(" ")[0]
        except Exception:
            vlc = "VLC non trovato"
        finestra = {}

        def tastiera():
            # chiude Informazioni e mostra la pagina con le scorciatoie di tastiera e mouse
            finestra["d"].accept()
            QTimer.singleShot(0, lambda: self.stack.setCurrentWidget(self.info_page))

        finestra["d"] = InformazioniDialog(
            pro.licenza(), APP_TITLE, VERSION, "Lettore di liste M3U con gruppi, ricerca e preferiti. tk-tv è solo un "
            "lettore: non contiene né fornisce canali.", badge_pixmap(136, 36), "#e11d48",
            dati=[("Motore video", vlc, "Incluso nel programma (VideoLAN, LGPL)."),
                  ("Le tue impostazioni", app_data_dir(), "Il link della tua lista resta solo su questo computer.")],
            url_sorgente=URL_SORGENTE, cartella_licenze=pro.cartella_licenze(),
            su_aggiornamenti=lambda: self.updates.check(manual=True),
            pulsanti=[("Tastiera e mouse", tastiera)], parent=self)
        return finestra["d"]

    def __init__(self):
        super().__init__()
        self.store = Store()
        self.logos = LogoLoader(self)
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(900, 600)
        self.all_channels = []
        self.loading = False
        self.load_generation = 0
        self.was_maximized = False
        self.mac_fs = None
        if sys.platform == "darwin":
            from tktv.macfs import MacFullScreen
            self.mac_fs = MacFullScreen(self)

        self.stack = QStackedWidget()
        self.stack.setObjectName("tkRoot")
        self.setCentralWidget(self.stack)
        self.channels_page = ChannelsPage(self.store, self.logos)
        self.player_page = PlayerPage(self.store)
        self.settings_page = SettingsPage()
        self.info_page = InfoPage()
        for p in (self.channels_page, self.player_page, self.settings_page, self.info_page):
            self.stack.addWidget(p)

        self.loader = _Loader(self)
        self.loader.done.connect(self._loaded)
        self.updates = UpdateManager(self)

        c = self.channels_page
        c.play.connect(self.play)
        c.open_app.connect(lambda app: QDesktopServices.openUrl(QUrl(app.url)))
        c.toggle_favorite.connect(self.toggle_favorite)
        c.reload_requested.connect(self.reload)
        c.settings_requested.connect(self.open_settings)
        c.info_requested.connect(self.show_info)
        c.update_requested.connect(self.updates.show_dialog)

        pl = self.player_page
        pl.back.connect(self.stop_playing)
        pl.fullscreen_toggled.connect(self.toggle_fullscreen)
        pl.toggle_favorite.connect(self.toggle_favorite)
        pl.lookup = self.lookup_number

        s = self.settings_page
        s.save.connect(self.load)
        s.back.connect(self.show_channels)
        s.resume_changed.connect(self._resume_changed)
        s.set_resume(self.store.resume_last)

        self.info_page.back.connect(self.show_channels)
        self.info_page.check_updates.connect(lambda: self.updates.check(manual=True))

        geo = self.store.settings.value("window/geometry")
        if isinstance(geo, QByteArray) and not geo.isEmpty():
            self.restoreGeometry(geo)
        else:
            self.resize(1280, 800)
        from tktv.tk_licenza_qt import dentro_lo_schermo
        dentro_lo_schermo(self)  # anche la misura salvata su uno schermo più grande resta dentro questo (MacBook)

        self._start()

    # ------------------------------------------------------------ avvio
    def _start(self):
        url = self.store.playlist_url
        cached = playlist.load_cache() if url else []
        if cached:
            self._set_channels(cached)
            self.show_channels()
            self.load(url, background=True)
            if self.store.resume_last and "--selftest" not in sys.argv:
                # dopo che la finestra è comparsa: il video di VLC ha bisogno della sua finestra nativa
                QTimer.singleShot(1200, self._resume)
        elif url:
            self.open_settings()
            self.load(url)
        else:
            self.open_settings()

    # ------------------------------------------------------------ playlist
    def load(self, url, background=False):
        self.load_generation += 1
        gen = self.load_generation
        self.loading = True
        if not background:
            self.settings_page.set_loading(True)
        self.channels_page.reload_btn.setEnabled(False)

        def work():
            try:
                self.loader.done.emit(gen, playlist.download(url), "")
            except Exception as exc:
                self.loader.done.emit(gen, None, str(exc) or "Errore sconosciuto")

        self._pending_url = url
        threading.Thread(target=work, daemon=True).start()

    def _loaded(self, gen, result, error):
        if gen != self.load_generation:
            return
        self.loading = False
        self.channels_page.reload_btn.setEnabled(True)
        self.settings_page.set_loading(False)
        if result is None:
            if self.stack.currentWidget() is self.settings_page or not self.all_channels:
                self.settings_page.set_error(error)
            else:
                self.channels_page.set_notice(f"Playlist non aggiornata ({error}): mostro l'ultima copia salvata.")
            return
        text, channels = result
        self.store.playlist_url = self._pending_url
        playlist.save_cache(text)
        self.channels_page.set_notice("")
        self._set_channels(channels)
        if self.stack.currentWidget() is self.settings_page:
            self.show_channels()

    def _set_channels(self, channels):
        self.all_channels = channels
        self.channels_page.set_channels(channels)

    def _resume(self):
        name = self.store.last_channel
        visible = self.channels_page.channels
        ch = next((c for c in visible if c.name == name), None)
        if ch is not None and self.stack.currentWidget() is self.channels_page:
            self.play(ch, visible)

    def _resume_changed(self, on):
        self.store.resume_last = on

    def reload(self):
        if self.store.playlist_url and not self.loading:
            self.load(self.store.playlist_url, background=True)

    # ------------------------------------------------------------ navigazione
    def show_channels(self):
        if not self.all_channels:
            self.open_settings()
            return
        self.stack.setCurrentWidget(self.channels_page)
        self.channels_page.focus_grid()

    def open_settings(self):
        self.settings_page.prepare(self.store.playlist_url, bool(self.all_channels))
        self.stack.setCurrentWidget(self.settings_page)

    def is_playing(self):
        return self.stack.currentWidget() is self.player_page

    # ------------------------------------------------------------ riproduzione
    def play(self, channel, channels):
        if channel not in channels:
            channels = self.channels_page.channels
        self.player_page.set_favorites(self.channels_page.favorites)
        self.stack.setCurrentWidget(self.player_page)
        self.player_page.start(channels, channels.index(channel))

    def stop_playing(self):
        self.player_page.stop()
        if self.is_full():
            self.toggle_fullscreen()
        self.show_channels()

    def lookup_number(self, number):
        visible = self.channels_page.channels
        for ch in visible:
            if ch.number == number:
                return ch, visible
        return None

    def is_full(self):
        return self.mac_fs.active if self.mac_fs is not None else self.isFullScreen()

    def toggle_fullscreen(self):
        if self.mac_fs is not None:
            if self.mac_fs.active:
                self.mac_fs.leave()
            else:
                self.mac_fs.enter()
            self.player_page.set_fullscreen(self.mac_fs.active)
            return
        if self.isFullScreen():
            if self.was_maximized:
                self.showMaximized()
            else:
                self.showNormal()
            self.player_page.set_fullscreen(False)
        else:
            self.was_maximized = self.isMaximized()
            self.showFullScreen()
            self.player_page.set_fullscreen(True)

    # ------------------------------------------------------------ preferiti
    def toggle_favorite(self, name):
        favs = self.store.toggle_favorite(name)
        self.channels_page.set_favorites(favs)
        self.player_page.set_favorites(favs)

    # ------------------------------------------------------------ aggiornamenti
    def show_update_button(self, version):
        self.channels_page.show_update(version)

    # ------------------------------------------------------------ chiusura
    def closeEvent(self, e):
        self.player_page.stop()
        if self.mac_fs is not None:
            self.mac_fs.leave()
        if not self.is_full():
            self.store.settings.setValue("window/geometry", self.saveGeometry())
        super().closeEvent(e)
