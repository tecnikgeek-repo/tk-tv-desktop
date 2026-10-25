"""Prova a schermo dello sviluppatore: carica la playlist, salva gli screenshot di lista, info e player.

Uso: python tests/demo.py <cartella_output> [nome canale]   (link in TKTV_TEST_URL)
Usa il profilo «test» (registro TecnikGeek\\tk-tv-player-test, %APPDATA%\\tk-tv-player-test), mai quello reale.
"""
import faulthandler
import os
import site
import sys

# se qualcosa si blocca o va in crash, stampa dove sono fermi i thread
faulthandler.enable(all_threads=True)
faulthandler.dump_traceback_later(int(os.environ.get("TKTV_DEMO_TIMEOUT", "40")), exit=True)

# profilo separato: mai toccare link e preferiti reali dell'utente
os.environ["TKTV_PROFILE"] = "test"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
site.addsitedir(os.path.join(ROOT, ".venv", "Lib", "site-packages"))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QTimer  # noqa: E402

from tktv.app import build  # noqa: E402

out = sys.argv[1]
name = sys.argv[2] if len(sys.argv) > 2 else "Rai 1"
os.makedirs(out, exist_ok=True)
app, win = build(sys.argv[:1])
win.store.volume = 0
win.move(80, 60)
win.resize(1280, 800)
win.show()
win.load(os.environ["TKTV_TEST_URL"])


def shot_screen(fname):
    g = win.frameGeometry()
    win.screen().grabWindow(0, g.x(), g.y(), g.width(), g.height()).save(os.path.join(out, fname))


steps = []


def at(ms, fn):
    steps.append((ms, fn))


at(5000, lambda: win.grab().save(os.path.join(out, "1-lista.png")))
at(5500, lambda: win.channels_page.sidebar.setCurrentRow(3))
at(6500, lambda: win.grab().save(os.path.join(out, "2-tutti.png")))
at(7000, lambda: win.stack.setCurrentWidget(win.info_page))
at(8000, lambda: win.grab().save(os.path.join(out, "3-info.png")))


def play():
    ch = next(c for c in win.all_channels if c.name == name)
    win.play(ch, win.channels_page.channels)


at(8500, play)
at(13000, lambda: shot_screen("4-player.png"))
at(19000, lambda: shot_screen("5-player-senza-comandi.png"))
at(19500, lambda: win.player_page.next())
at(23000, lambda: shot_screen("6-zapping.png"))
at(23500, win.toggle_fullscreen)
at(27000, lambda: win.screen().grabWindow(0).save(os.path.join(out, "7-schermo-intero.png")))
at(27500, win.toggle_fullscreen)
at(28500, win.stop_playing)
at(29500, lambda: win.grab().save(os.path.join(out, "8-ritorno.png")))
at(30000, app.quit)
def traced(ms, fn):
    def run():
        print(f"[{ms}] inizio {getattr(fn, '__name__', fn)}", file=sys.stderr, flush=True)
        fn()
        print(f"[{ms}] fine", file=sys.stderr, flush=True)
    return run


app.aboutToQuit.connect(lambda: print("aboutToQuit", file=sys.stderr, flush=True))
for ms, fn in steps:
    QTimer.singleShot(ms, traced(ms, fn))
code = app.exec()
print(f"exec terminato: {code}", file=sys.stderr, flush=True)
sys.exit(code)
