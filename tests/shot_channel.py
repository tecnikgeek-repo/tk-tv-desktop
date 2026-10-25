"""Apre un canale a schermo e fotografa il player dopo N secondi: python tests/shot_channel.py <out.png> <canale> [secondi]."""
import os
import site
import sys

os.environ["TKTV_PROFILE"] = "test"  # mai le impostazioni reali
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
site.addsitedir(os.path.join(ROOT, ".venv", "Lib", "site-packages"))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QTimer  # noqa: E402

from tktv.app import build  # noqa: E402

out, name = sys.argv[1], sys.argv[2]
wait = int(sys.argv[3]) if len(sys.argv) > 3 else 10
app, win = build(sys.argv[:1])
win.store.volume = 0
win.move(80, 60)
win.resize(1280, 800)
win.show()
win.load(os.environ["TKTV_TEST_URL"])


def play():
    ch = next(c for c in win.all_channels if c.name == name)
    win.play(ch, win.channels_page.channels)


def shot():
    g = win.frameGeometry()
    win.screen().grabWindow(0, g.x(), g.y(), g.width(), g.height()).save(out)
    win.stop_playing()
    app.quit()


QTimer.singleShot(4000, play)
QTimer.singleShot(4000 + wait * 1000, shot)
sys.exit(app.exec())
