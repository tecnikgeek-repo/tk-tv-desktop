"""Prova le fonti dei loghi delle app di streaming e crea un foglio di confronto: python tests/probe_app_icons.py <out.png>."""
import os
import site
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
site.addsitedir(os.path.join(ROOT, ".venv", "Lib", "site-packages"))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter  # noqa: E402

from tktv.playlist import _ssl_context  # noqa: E402
from tktv.streaming import CATALOGO  # noqa: E402

app = QGuiApplication(sys.argv)
SOURCES = {
    "google256": lambda host: f"https://www.google.com/s2/favicons?domain={host}&sz=256",
    "touch": lambda host: f"https://{host}/apple-touch-icon.png",
}
cell = 96
sheet = QImage(cell * len(SOURCES) + 180, cell * len(CATALOGO), QImage.Format.Format_RGB32)
sheet.fill(QColor("#0f172a"))
p = QPainter(sheet)
p.setPen(QColor("white"))
for row, a in enumerate(CATALOGO):
    host = a.url.split("/")[2]
    p.drawText(QRect(4, row * cell, 170, cell), Qt.AlignmentFlag.AlignVCenter, a.nome)
    for col, (key, make) in enumerate(SOURCES.items()):
        url = make(host)
        img = QImage()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10, context=_ssl_context()) as r:
                img.loadFromData(r.read())
        except Exception:
            pass
        info = "-" if img.isNull() else f"{img.width()}"
        print(f"{a.nome:18} {key:10} {info}")
        if not img.isNull():
            p.drawImage(QRect(180 + col * cell + 8, row * cell + 8, 80, 80), img)
p.end()
sheet.save(sys.argv[1])
