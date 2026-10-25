"""Genera le icone: assets/tk-tv.ico (Windows, multi-risoluzione) e assets/tk-tv.png."""
import os
import site
import struct
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
site.addsitedir(os.path.join(ROOT, ".venv", "Lib", "site-packages"))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from tktv.icon import render_icon  # noqa: E402

ASSETS = os.path.join(ROOT, "assets")
os.makedirs(ASSETS, exist_ok=True)


def png_bytes(img):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


# ICO multi-risoluzione (PNG incapsulati)
sizes = [16, 24, 32, 48, 64, 128, 256]
pngs = [png_bytes(render_icon(s)) for s in sizes]
header = struct.pack("<HHH", 0, 1, len(sizes))
offset = 6 + 16 * len(sizes)
entries = b""
data = b""
for s, png in zip(sizes, pngs):
    entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(png), offset + len(data))
    data += png
with open(os.path.join(ASSETS, "tk-tv.ico"), "wb") as fh:
    fh.write(header + entries + data)
render_icon(256).save(os.path.join(ASSETS, "tk-tv.png"))
print("icone generate")
