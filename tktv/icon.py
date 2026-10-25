"""Icona di tk-tv disegnata via codice: la stessa «LiveTv» dell'app Android (TV con antenna e play)."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap


def live_tv_path(x, y, unit):
    """Tracciato del simbolo LiveTv (griglia Material 24x24) con origine (x, y) e lato unità `unit`."""
    def pt(px, py):
        return QPointF(x + px * unit, y + py * unit)

    body = QPainterPath()
    body.setFillRule(Qt.FillRule.OddEvenFill)
    body.addRoundedRect(QRectF(pt(1, 6), pt(23, 22)), 2 * unit, 2 * unit)
    body.addRect(QRectF(pt(3, 8), pt(21, 20)))
    play = QPainterPath()
    play.moveTo(pt(9, 10))
    play.lineTo(pt(9, 18))
    play.lineTo(pt(16, 14))
    play.closeSubpath()
    return body, play


def paint_live_tv(p, rect, color):
    unit = min(rect.width(), rect.height()) / 24.0
    x = rect.x() + (rect.width() - 24 * unit) / 2
    y = rect.y() + (rect.height() - 24 * unit) / 2
    body, play = live_tv_path(x, y, unit)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(body)
    p.drawPath(play)
    pen = QPen(QColor(color), 1.1 * unit, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(x + 12 * unit, y + 6 * unit), QPointF(x + 8 * unit, y + 2.2 * unit))
    p.drawLine(QPointF(x + 12 * unit, y + 6 * unit), QPointF(x + 16 * unit, y + 2.2 * unit))


def render_icon(size):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 256.0
    grad = QLinearGradient(QPointF(0, 0), QPointF(size, size))
    grad.setColorAt(0, QColor("#e11d48"))
    grad.setColorAt(1, QColor("#be123c"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(QRectF(8 * s, 8 * s, 240 * s, 240 * s), 56 * s, 56 * s)
    paint_live_tv(p, QRectF(40 * s, 36 * s, 176 * s, 176 * s), "#ffffff")
    p.end()
    return img


def app_icon():
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(render_icon(size)))
    return icon


def badge_pixmap(size, radius=12):
    """Riquadro con gradiente accent e simbolo TV bianco (usato nelle testate)."""
    ratio = 2
    img = QImage(size * ratio, size * ratio, QImage.Format.Format_ARGB32)
    img.setDevicePixelRatio(ratio)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(QPointF(0, 0), QPointF(size, size))
    grad.setColorAt(0, QColor("#e11d48"))
    grad.setColorAt(1, QColor("#be123c"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
    m = size * 0.2
    paint_live_tv(p, QRectF(m, m, size - 2 * m, size - 2 * m), "#ffffff")
    p.end()
    return QPixmap.fromImage(img)
