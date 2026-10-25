"""Crea assets/tk-tv.icns per il Mac dalla stessa icona disegnata via codice (tktv/icon.py).

Le icone macOS hanno un margine: il disegno occupa circa 824 px su 1024.
Uso: python mac/make_icns.py   (richiede iconutil, incluso in macOS)
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])

from tktv.icon import render_icon  # noqa: E402


def mac_icon(px):
    img = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    inner = round(px * 824 / 1024)
    pad = (px - inner) // 2
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawImage(QRect(pad, pad, inner, inner), render_icon(inner))
    p.end()
    return img


iconset = os.path.join(ROOT, "assets", "tk-tv.iconset")
shutil.rmtree(iconset, ignore_errors=True)
os.makedirs(iconset)
for size in (16, 32, 128, 256, 512):
    mac_icon(size).save(os.path.join(iconset, f"icon_{size}x{size}.png"))
    mac_icon(size * 2).save(os.path.join(iconset, f"icon_{size}x{size}@2x.png"))
subprocess.run(["iconutil", "-c", "icns", iconset, "-o", os.path.join(ROOT, "assets", "tk-tv.icns")], check=True)
shutil.rmtree(iconset)
print("icona Mac generata")
