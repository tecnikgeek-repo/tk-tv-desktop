"""Loghi dei canali (tvg-logo): scaricati in background, con cache su disco e in memoria."""
import os

from PySide6.QtCore import QObject, QUrl, Signal, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkDiskCache, QNetworkReply, QNetworkRequest

from tktv.util import app_data_dir

MAX_PARALLEL = 6
LOGO_BOX = 160  # lato massimo in pixel dei loghi in memoria


class LogoLoader(QObject):
    loaded = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.net = QNetworkAccessManager(self)
        cache = QNetworkDiskCache(self)
        cache.setCacheDirectory(os.path.join(app_data_dir(), "loghi"))
        cache.setMaximumCacheSize(80 * 1024 * 1024)
        self.net.setCache(cache)
        self.pixmaps = {}
        self.failed = set()
        self.queue = []
        self.running = 0
        self.pending = set()

    def get(self, url):
        """Pixmap del logo se già pronto; altrimenti lo mette in coda e ritorna None."""
        if not url or not url.lower().startswith(("http://", "https://")):
            return None  # solo loghi dal web: mai file locali o altri schemi indicati dalla lista
        pm = self.pixmaps.get(url)
        if pm is not None:
            return pm
        if url not in self.failed and url not in self.pending:
            self.pending.add(url)
            self.queue.append(url)
            self._pump()
        return None

    def _pump(self):
        while self.running < MAX_PARALLEL and self.queue:
            url = self.queue.pop()  # prima gli ultimi richiesti: sono quelli a schermo
            req = QNetworkRequest(QUrl(url))
            req.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute,
                             QNetworkRequest.CacheLoadControl.PreferCache)
            req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
            req.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, "Mozilla/5.0 tk-tv")
            req.setTransferTimeout(15000)
            reply = self.net.get(req)
            self.running += 1
            reply.finished.connect(lambda r=reply, u=url: self._done(r, u))

    def _done(self, reply, url):
        self.running -= 1
        self.pending.discard(url)
        img = QImage()
        if reply.error() == QNetworkReply.NetworkError.NoError:
            img.loadFromData(reply.readAll())
        reply.deleteLater()
        if img.isNull():
            self.failed.add(url)
        else:
            if img.width() > LOGO_BOX or img.height() > LOGO_BOX:
                img = img.scaled(LOGO_BOX, LOGO_BOX, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            self.pixmaps[url] = QPixmap.fromImage(img)
            self.loaded.emit(url)
        self._pump()
