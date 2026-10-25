"""Schermo intero su Mac senza Spazio separato (AppKit via ctypes, nessuna libreria in più).

Lo schermo intero nativo di macOS sposta la finestra in uno Spazio tutto suo con un'animazione:
la finestra dei comandi sopra il video (player.Overlay) resterebbe indietro. Qui la finestra
resta dov'è: diventa senza bordi, grande quanto lo schermo, con Dock e barra dei menu nascosti.
"""
import ctypes
import ctypes.util

_objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
ctypes.cdll.LoadLibrary(ctypes.util.find_library("AppKit"))
_objc.objc_getClass.restype = ctypes.c_void_p
_objc.objc_getClass.argtypes = [ctypes.c_char_p]
_objc.sel_registerName.restype = ctypes.c_void_p
_objc.sel_registerName.argtypes = [ctypes.c_char_p]
_SEND = ctypes.cast(_objc.objc_msgSend, ctypes.c_void_p).value

# NSApplicationPresentationHideDock | NSApplicationPresentationHideMenuBar
HIDE_DOCK_AND_MENU = (1 << 1) | (1 << 3)
BORDERLESS = 0


class NSRect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double), ("w", ctypes.c_double), ("h", ctypes.c_double)]


def _msg(restype, *argtypes):
    return ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *argtypes)(_SEND)


def _sel(name):
    return _objc.sel_registerName(name.encode())


def _app():
    return _msg(ctypes.c_void_p)(_objc.objc_getClass(b"NSApplication"), _sel("sharedApplication"))


def _nswindow(widget):
    view = int(widget.winId())  # su Mac winId() = NSView
    return _msg(ctypes.c_void_p)(view, _sel("window"))


class MacFullScreen:
    def __init__(self, widget):
        self.widget = widget
        self.active = False
        self._mask = None
        self._geometry = None
        self._maximized = False

    def enter(self):
        if self.active:
            return
        w = self.widget
        self._maximized = w.isMaximized()
        self._geometry = w.geometry()
        win = _nswindow(w)
        self._mask = _msg(ctypes.c_ulong)(win, _sel("styleMask"))
        _msg(None, ctypes.c_ulong)(_app(), _sel("setPresentationOptions:"), HIDE_DOCK_AND_MENU)
        _msg(None, ctypes.c_ulong)(win, _sel("setStyleMask:"), BORDERLESS)
        # coordinate AppKit: origine in basso a sinistra dello schermo principale
        from PySide6.QtGui import QGuiApplication
        g = w.screen().geometry()
        top = QGuiApplication.primaryScreen().geometry().height()
        frame = NSRect(g.x(), top - g.y() - g.height(), g.width(), g.height())
        _msg(None, NSRect, ctypes.c_bool)(win, _sel("setFrame:display:"), frame, True)
        self.active = True

    def leave(self):
        if not self.active:
            return
        w = self.widget
        win = _nswindow(w)
        _msg(None, ctypes.c_ulong)(_app(), _sel("setPresentationOptions:"), 0)
        _msg(None, ctypes.c_ulong)(win, _sel("setStyleMask:"), self._mask)
        self.active = False
        if self._maximized:
            w.showMaximized()
        else:
            w.setGeometry(self._geometry)
