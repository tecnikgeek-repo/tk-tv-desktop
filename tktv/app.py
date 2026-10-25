"""Avvio dell'applicazione."""
import os
import sys
import time
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from tktv import APP_NAME, APP_TITLE, VERSION
from tktv.util import app_data_dir


def _install_excepthook():
    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            with open(os.path.join(app_data_dir(), "errori.log"), "a", encoding="utf-8") as fh:
                fh.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] v{VERSION}\n{text}")
        except OSError:
            pass
        if QApplication.instance() is not None:
            QMessageBox.warning(None, APP_TITLE, f"Si è verificato un errore imprevisto:\n\n{exc}\n\n"
                                                 "Il dettaglio è stato salvato in errori.log.")
        else:
            sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = hook


def _refresh_install():
    """Collegamenti e «App installate» allineati alla versione appena arrivata con l'aggiornamento."""
    import threading

    def work():
        try:
            from tktv.zipsetup import refresh_after_update
            refresh_after_update()
        except Exception:
            pass  # non deve mai impedire l'uso dell'app

    threading.Thread(target=work, daemon=True).start()


def main():
    if "--warm-vlc" in sys.argv:
        from tktv.engine import warm_cli
        sys.exit(warm_cli())
    if "--install-zip" in sys.argv:
        from tktv.zipsetup import run as install_from_zip
        sys.exit(install_from_zip(sys.argv))
    if "--uninstall" in sys.argv:
        from tktv.uninstall import run as uninstall
        sys.exit(uninstall())
    if "--update-test" in sys.argv:
        from tktv.updater import cli_update_test
        sys.exit(cli_update_test(sys.argv))

    _install_excepthook()
    app, win = build(sys.argv)

    if "--selftest" in sys.argv:
        # verifica del pacchetto: avvia libVLC, salva uno screenshot della finestra ed esce
        out = sys.argv[sys.argv.index("--selftest") + 1]
        win.move(-4000, -4000)
        win.resize(1280, 800)
        win.show()

        def finish():
            from tktv import engine
            ok = True
            try:
                engine.instance().media_player_new().release()
            except Exception as exc:
                ok = False
                with open(out + ".err", "w", encoding="utf-8") as fh:
                    fh.write(str(exc))
            if ok:
                win.grab().save(out)
            app.quit()

        QTimer.singleShot(3000, finish)
        sys.exit(app.exec())

    win.show()
    from tktv import engine
    engine.warm_up_async()
    if sys.platform == "win32":
        QTimer.singleShot(2000, _refresh_install)
    from tktv import pro

    def dopo_il_benvenuto():
        # benvenuto (una volta sola) con la finestra già visibile: aggiornamenti e statistiche solo dopo la risposta
        pro.benvenuto(win)
        # controllo aggiornamenti in background (al massimo ogni 12 ore)
        QTimer.singleShot(5000, win.updates.check)
        # segnale giornaliero in sottofondo: parte solo se l'utente ha detto sì alle statistiche
        if getattr(app, "licenza", None) is not None:
            QTimer.singleShot(6000, app.licenza.avvia)
        # invito al caffè: mai sopra un canale che si sta guardando
        pro.invito(win, lambda: not win.is_playing())

    QTimer.singleShot(0, dopo_il_benvenuto)
    sys.exit(app.exec())


def build(argv):
    """Crea QApplication e finestra principale (usato anche dai test)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TecnikGeek.tk-tv-player")
        except Exception:
            pass

    app = QApplication(argv)
    # licenza prima della finestra: consenso alle statistiche, benvenuto e invito al caffè la leggono
    from tktv import pro
    app.licenza = pro.crea_licenza(VERSION)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("TecnikGeek")
    app.setApplicationDisplayName(APP_TITLE)
    app.setStyle("Fusion")
    from PySide6.QtCore import QLibraryInfo, QTranslator
    translator = QTranslator(app)
    if translator.load("qtbase_it", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    except Exception:
        pass

    from tktv.icon import app_icon
    from tktv.mainwindow import MainWindow
    from tktv import style as S
    from tktv.style import QSS

    S.load_fonts()
    font = S.ui_font()
    font.setPixelSize(15)
    app.setFont(font)
    app.setStyleSheet(QSS)
    app.setWindowIcon(app_icon())
    return app, MainWindow()
