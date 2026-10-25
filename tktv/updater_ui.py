"""Interfaccia degli aggiornamenti: controllo in background e finestra di aggiornamento."""
import html
import os
import sys
import time

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QVBoxLayout

from tktv import APP_TITLE, VERSION
from tktv import style as S
from tktv.updater import (
    CHECK_INTERVAL, MANIFEST_URL, apply_update, asset_for, download, download_dir, fetch_manifest, install_kind,
    is_newer,
)
from tktv.util import human_size


class CheckThread(QThread):
    checked = Signal(object, str)

    def __init__(self, url=MANIFEST_URL, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        import urllib.error
        try:
            self.checked.emit(fetch_manifest(self.url), "")
        except urllib.error.HTTPError as exc:
            # il server risponde: la connessione c'è, è il file degli aggiornamenti che manca o non va
            self.checked.emit(None, f"Il server degli aggiornamenti non risponde correttamente (errore {exc.code}).\n"
                                    "Riprova più tardi.")
        except Exception as exc:
            self.checked.emit(None, f"Verifica la connessione a internet.\n\n{exc}")


class DownloadThread(QThread):
    progress = Signal(float, float)
    ok = Signal(str)
    failed = Signal(str)

    def __init__(self, url, dest, sha256, parent=None):
        super().__init__(parent)
        self.url, self.dest, self.sha256 = url, dest, sha256
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            download(self.url, self.dest, self.sha256, lambda d, t: self.progress.emit(float(d), float(t)),
                     lambda: self._cancel)
            self.ok.emit(self.dest)
        except InterruptedError:
            self.failed.emit("")
        except Exception as exc:
            self.failed.emit(str(exc))


class UpdateDialog(QDialog):
    def __init__(self, window, manifest):
        super().__init__(window)
        self.window = window
        self.manifest = manifest
        self.asset = asset_for(manifest)
        self.thread = None
        new = manifest["version"]
        self.setWindowTitle("Aggiornamento disponibile")
        self.setMinimumWidth(480)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 18)
        lay.setSpacing(12)
        title = QLabel(f"<div style='font-size:17px;font-weight:800'>È disponibile {APP_TITLE} {html.escape(new)}</div>"
                       f"<div style='color:{S.GRAY300}'>Stai usando la versione {VERSION}"
                       + (f" · pubblicata il {html.escape(manifest['date'])}" if manifest.get("date") else "")
                       + "</div>")
        lay.addWidget(title)

        notes = manifest.get("notes") or []
        if notes:
            items = "".join(f"<li>{html.escape(str(n))}</li>" for n in notes)
            box = QLabel(f"<b>Novità</b><ul style='margin-left:-18px'>{items}</ul>")
            box.setWordWrap(True)
            box.setStyleSheet(f"background:{S.NAVY2}; border-radius:10px; padding:10px;")
            lay.addWidget(box)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.hide()
        lay.addWidget(self.bar)
        self.status = QLabel("")
        self.status.setObjectName("soft")
        lay.addWidget(self.status)

        row = QHBoxLayout()
        self.skip_btn = QPushButton("Salta questa versione")
        self.skip_btn.setObjectName("flat")
        self.later_btn = QPushButton("Più tardi")
        self.update_btn = QPushButton("Aggiorna ora")
        self.update_btn.setObjectName("accent")
        self.update_btn.setDefault(True)
        row.addWidget(self.skip_btn)
        row.addStretch(1)
        row.addWidget(self.later_btn)
        row.addWidget(self.update_btn)
        lay.addLayout(row)

        self.skip_btn.clicked.connect(self._skip)
        self.later_btn.clicked.connect(self._later)
        self.update_btn.clicked.connect(self._start)
        if self.asset is None:
            self.update_btn.setEnabled(False)
            self.status.setText(f"Questa versione non è ancora disponibile per {'Mac' if sys.platform == 'darwin' else 'Windows'}.")

    def _skip(self):
        self.window.store.settings.setValue("update/skip_version", self.manifest["version"])
        self.reject()

    def _later(self):
        if self.thread is not None:
            self.thread.cancel()
            self.thread.wait(3000)
        self.reject()

    def _start(self):
        if install_kind() is None:
            QMessageBox.information(self, APP_TITLE, "Stai usando la versione di sviluppo di tk-tv: l'aggiornamento "
                                                     "automatico funziona solo con la versione installata.")
            return
        self.update_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        self.later_btn.setText("Annulla")
        self.bar.show()
        self.bar.setRange(0, 0)
        self.status.setText("Download in corso…")
        name = os.path.basename(self.asset["url"].split("?")[0])
        self.thread = DownloadThread(self.asset["url"], os.path.join(download_dir(), name), self.asset.get("sha256"), self)
        self.thread.progress.connect(self._progress)
        self.thread.ok.connect(self._downloaded)
        self.thread.failed.connect(self._failed)
        self.thread.start()

    def _progress(self, done, total):
        if total > 0:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(done * 1000 / total))
            self.status.setText(f"Download in corso… {human_size(done)} di {human_size(total)}")
        else:
            self.status.setText(f"Download in corso… {human_size(done)}")

    def _downloaded(self, path):
        self.status.setText("Installazione dell'aggiornamento…")
        self.later_btn.setEnabled(False)
        try:
            apply_update(path, new_version=self.manifest["version"])
        except Exception as exc:
            self._failed(str(exc))
            return
        QTimer.singleShot(300, QApplication.instance().quit)

    def _failed(self, message):
        self.bar.hide()
        self.update_btn.setEnabled(True)
        self.skip_btn.setEnabled(True)
        self.later_btn.setEnabled(True)
        self.later_btn.setText("Più tardi")
        self.thread = None
        if message:
            self.status.setText("")
            QMessageBox.warning(self, APP_TITLE, f"Aggiornamento non riuscito:\n{message}")
        else:
            self.status.setText("Download annullato.")


class UpdateManager:
    """Collega il controllo aggiornamenti alla finestra principale."""

    def __init__(self, window):
        self.window = window
        self.thread = None
        self.manifest = None

    def check(self, manual=False):
        settings = self.window.store.settings
        if not manual:
            last = settings.value("update/last_check", 0, type=float)
            if time.time() - last < CHECK_INTERVAL:
                cached = settings.value("update/available", "", type=str)
                if cached and is_newer(cached):
                    self.window.show_update_button(cached)
                return
        if self.thread is not None and self.thread.isRunning():
            return
        self.thread = CheckThread(parent=self.window)
        self.thread.checked.connect(lambda m, err: self._checked(m, err, manual))
        self.thread.start()

    def _checked(self, manifest, error, manual):
        settings = self.window.store.settings
        if manifest is None:
            if manual:
                QMessageBox.warning(self.window, APP_TITLE, f"Impossibile controllare gli aggiornamenti.\n{error}")
            return
        settings.setValue("update/last_check", time.time())
        version = str(manifest["version"])
        if not is_newer(version):
            settings.setValue("update/available", "")
            self.window.show_update_button(None)
            if manual:
                QMessageBox.information(self.window, APP_TITLE, f"Hai già l'ultima versione di tk-tv ({VERSION}).")
            return
        self.manifest = manifest
        settings.setValue("update/available", version)
        self.window.show_update_button(version)
        skipped = settings.value("update/skip_version", "", type=str) == version
        # mai interrompere la visione con una finestra: resta il tasto verde in alto
        if manual or (not skipped and not self.window.is_playing() and QApplication.activeModalWidget() is None):
            self.show_dialog()

    def show_dialog(self):
        if self.manifest is None:
            self.check(manual=True)
            return
        UpdateDialog(self.window, self.manifest).exec()
