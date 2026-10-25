"""Screenshot rapido della lista canali: python tests/shot_list.py <file.png>   (link in TKTV_TEST_URL)."""
import os
import site
import sys

# profilo separato: mai toccare link e preferiti reali dell'utente
os.environ["TKTV_PROFILE"] = "test"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
site.addsitedir(os.path.join(ROOT, ".venv", "Lib", "site-packages"))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QTimer  # noqa: E402

from tktv.app import build  # noqa: E402

app, win = build(sys.argv[:1])
win.move(-4000, -4000)
win.resize(1280, 800)
win.show()
win.load(os.environ["TKTV_TEST_URL"])
def open_section(key):
    sb = win.channels_page.sidebar
    for i in range(sb.count()):
        if sb.item(i).data(0x0100) == key:  # Qt.UserRole
            sb.setCurrentRow(i)


if len(sys.argv) > 2:  # sezione da aprire, es. «app» o «g:Notizie»
    QTimer.singleShot(4000, lambda: open_section(sys.argv[2]))
# fuori schermo la griglia si disegna solo al grab: il primo avvia il download dei loghi
QTimer.singleShot(6000, win.grab)
QTimer.singleShot(11000, lambda: win.grab().save(sys.argv[1]))
QTimer.singleShot(11500, lambda: win.stack.setCurrentWidget(win.info_page))
QTimer.singleShot(12500, lambda: (win.grab().save(sys.argv[1].replace(".png", "-info.png")), app.quit()))
sys.exit(app.exec())
