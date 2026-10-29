"""Collaudo del pacchetto: riproduce davvero un video di prova con il libVLC incluso.

Uso: tk-tv --selftest-video <video.ts> <risultato.txt>

Il video (generato al volo dallo script di build, contenuto neutro: barre colorate e audio muto) viene servito
da un piccolo server http locale con una lista M3U di prova di un solo canale, e passa dagli stessi pezzi
dell'uso normale: download della lista, finestra principale, pagina del player, libVLC con i suoi plugin.
Con uno schermo X11 (anche XWayland) il video va nella finestra vera, che passa anche a schermo intero
per qualche secondo e poi si chiude da sola; senza schermo (QT_QPA_PLATFORM=offscreen) va nell'uscita
video «finta» di VLC. Il risultato inizia con «OK» oppure con «ERRORE».
"""
import functools
import http.server
import os
import shutil
import sys
import tempfile
import threading
import time

DURATA_MASSIMA_S = 40


class _Quieto(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def _librerie_vlc_caricate():
    """(percorso di libvlccore, numero di plugin caricati, plugin presi da fuori dal pacchetto, uscite audio/video
    caricate) da /proc/self/maps."""
    core, plugins, estranei = "", set(), set()
    try:
        with open("/proc/self/maps", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                path = line.split(None, 5)[-1].strip() if line.count(" ") >= 5 else ""
                if "libvlccore.so" in path:
                    core = path
                elif path.endswith("_plugin.so"):
                    plugins.add(path)
    except OSError:
        pass
    from tktv import engine
    mia = os.path.realpath(engine.vlc_dir() or "/nessuna")
    for p in plugins:
        if not os.path.realpath(p).startswith(mia + os.sep):
            estranei.add(p)
    uscite = sorted(os.path.basename(p)[3:-len("_plugin.so")] for p in plugins
                    if os.path.basename(os.path.dirname(p)) in ("video_output", "audio_output"))
    return core, len(plugins), sorted(estranei), uscite


def _immagine_video(page, path):
    """Legge dal server X i punti dell'area del video (il contenuto disegnato da VLC) e ritorna la quota di punti
    non neri. Si legge la finestra principale con XGetImage: la cattura di Qt passa dalla finestra radice, che su
    XWayland è vuota (nera), e la finestra figlia del video letta da sola risulta nera."""
    import ctypes

    class XImage(ctypes.Structure):
        _fields_ = [("width", ctypes.c_int), ("height", ctypes.c_int), ("xoffset", ctypes.c_int),
                    ("format", ctypes.c_int), ("data", ctypes.POINTER(ctypes.c_ubyte)), ("byte_order", ctypes.c_int),
                    ("bitmap_unit", ctypes.c_int), ("bitmap_bit_order", ctypes.c_int), ("bitmap_pad", ctypes.c_int),
                    ("depth", ctypes.c_int), ("bytes_per_line", ctypes.c_int), ("bits_per_pixel", ctypes.c_int),
                    ("red_mask", ctypes.c_ulong), ("green_mask", ctypes.c_ulong), ("blue_mask", ctypes.c_ulong)]

    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QColor, QImage
    top = page.window()
    pos = page.video.mapTo(top, QPoint(0, 0))
    w, h = page.video.width(), page.video.height()
    try:
        x11 = ctypes.CDLL("libX11.so.6")
    except OSError:
        return 0.0
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XGetImage.restype = ctypes.POINTER(XImage)
    x11.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_uint,
                              ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    dpy = x11.XOpenDisplay(None)
    if not dpy:
        return 0.0
    try:
        ptr = x11.XGetImage(dpy, int(top.winId()), pos.x(), pos.y(), w, h, ctypes.c_ulong(-1).value, 2)  # ZPixmap
        if not ptr or ptr.contents.bits_per_pixel != 32:
            return 0.0
        im = ptr.contents
        anteprima = QImage(48, 30, QImage.Format.Format_RGB32)
        colorati = 0
        for j in range(30):
            for i in range(48):
                x, y = int(im.width * (i + 0.5) / 48), int(im.height * (j + 0.5) / 30)
                o = y * im.bytes_per_line + x * 4
                b, g, r = im.data[o], im.data[o + 1], im.data[o + 2]
                anteprima.setPixelColor(i, j, QColor(r, g, b))
                colorati += r + g + b > 90
        anteprima.scaled(480, 300).save(path)
        return colorati / (48 * 30)
    finally:
        x11.XCloseDisplay(dpy)


def run(argv):
    i = argv.index("--selftest-video")
    video, out = os.path.abspath(argv[i + 1]), os.path.abspath(argv[i + 2])
    os.environ.setdefault("TKTV_PROFILE", "selftest")  # mai le impostazioni vere dell'utente
    righe, errori = [], []

    cartella = tempfile.mkdtemp(prefix="tktv-selftest-")
    shutil.copyfile(video, os.path.join(cartella, "prova.ts"))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quieto, directory=cartella))
    porta = server.server_address[1]
    with open(os.path.join(cartella, "prova.m3u"), "w", encoding="utf-8") as fh:
        fh.write("#EXTM3U\n#EXTINF:-1 tvg-chno=\"1\" group-title=\"Prova\",Canale di prova\n"
                 f"http://127.0.0.1:{porta}/prova.ts\n")
    threading.Thread(target=server.serve_forever, daemon=True).start()

    from tktv import engine, playlist
    from tktv.app import build
    app, win = build(argv)
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QGuiApplication
    finestra = QGuiApplication.platformName() == "xcb"
    righe.append(f"piattaforma Qt: {QGuiApplication.platformName()} (WAYLAND_DISPLAY="
                 f"{os.environ.get('WAYLAND_DISPLAY', '-')}, DISPLAY={os.environ.get('DISPLAY', '-')})")
    # audio sempre muto (il video di prova ha l'audio silenzioso); senza schermo anche il video è «finto»
    engine.EXTRA_ARGS = [] if finestra else ["--vout=vdummy", "--aout=adummy"]
    if not os.environ.get("XDG_RUNTIME_DIR"):
        engine.EXTRA_ARGS = list(dict.fromkeys(engine.EXTRA_ARGS + ["--aout=adummy"]))

    try:
        _testo, canali = playlist.download(f"http://127.0.0.1:{porta}/prova.m3u")
        righe.append(f"lista di prova: {len(canali)} canale ({canali[0].name})")
    except Exception as exc:  # noqa: BLE001
        canali = []
        errori.append(f"lista di prova non letta: {exc}")

    stato = {"inizio": time.time(), "tempi": [], "vout": 0, "fase": "gioca", "fs": None, "inib": None}
    page = win.player_page

    def fine():
        try:
            page.stop()
            if win.is_full():
                win.toggle_fullscreen()
        except Exception:  # noqa: BLE001
            pass
        from tktv import player
        if sys.platform.startswith("linux") and player.screen_kept_on():
            errori.append("inibizione del salvaschermo non tolta dopo lo stop")
        app.quit()

    def controlla():
        mp = page.mp
        trascorso = time.time() - stato["inizio"]
        if mp is not None:
            t = mp.get_time()
            if t is not None and t >= 0:
                stato["tempi"].append((trascorso, t))
            stato["vout"] = max(stato["vout"], mp.has_vout() or 0)
        tempi = stato["tempi"]
        avanzato = len(tempi) >= 2 and tempi[-1][1] - tempi[0][1] >= 3000
        if stato["fase"] == "gioca" and avanzato:
            from tktv import player
            stato["inib"] = player.screen_kept_on()
            stato["uscite"] = _librerie_vlc_caricate()[3]
            if finestra:
                stato["immagine"] = _immagine_video(page, os.path.splitext(out)[0] + "-finestra.png")
                stato["fase"] = "schermo intero"
                win.toggle_fullscreen()
                stato["t_fs"] = time.time()
            else:
                stato["fase"] = "fatto"
        elif stato["fase"] == "schermo intero" and time.time() - stato["t_fs"] > 2.5:
            # lo schermo è quello dove sta il video (con più monitor non sempre win.screen() è già aggiornato)
            from PySide6.QtCore import QPoint, QRect
            o = page.overlay
            video = QRect(page.video.mapToGlobal(QPoint(0, 0)), page.video.size())
            schermo = QGuiApplication.screenAt(video.center()) or win.screen()
            scr = schermo.geometry()
            stato["fs"] = (win.isFullScreen() and video == scr,
                           o is not None and o.isVisible() and o.geometry() == video,
                           f"{scr.getRect()}", o.geometry().getRect() if o is not None else None)
            stato["immagine_fs"] = _immagine_video(page, os.path.splitext(out)[0] + "-schermo-intero.png")
            win.toggle_fullscreen()
            stato["fase"] = "fatto"
        if stato["fase"] == "fatto" or trascorso > DURATA_MASSIMA_S:
            timer.stop()
            QTimer.singleShot(800, fine)

    timer = QTimer(interval=250, timeout=controlla)

    def avvia():
        if not canali:
            app.quit()
            return
        win.play(canali[0], canali)
        timer.start()

    win.resize(960, 600)
    win.show()
    QTimer.singleShot(500, avvia)
    app.exec()
    server.shutdown()

    # --- esito
    core, n_plugin, estranei, _u = _librerie_vlc_caricate()
    try:
        ver = engine.load().libvlc_get_version().decode()
    except Exception as exc:  # noqa: BLE001
        ver = f"non caricato ({exc})"
    righe.append(f"libVLC {ver}")
    righe.append(f"libvlccore: {core or 'non caricata'}")
    righe.append(f"plugin caricati: {n_plugin}, fuori dal pacchetto: {len(estranei)}")
    mia = os.path.realpath(engine.vlc_dir() or "/nessuna")
    if not core or not os.path.realpath(core).startswith(mia + os.sep):
        errori.append("libvlccore non è quella del pacchetto")
    if estranei:
        errori.append("plugin VLC presi dal sistema: " + ", ".join(estranei[:5]))
    tempi = stato["tempi"]
    if tempi:
        righe.append(f"tempo del video: da {tempi[0][1]} a {tempi[-1][1]} ms in {tempi[-1][0] - tempi[0][0]:.1f} s")
    if not tempi or tempi[-1][1] - tempi[0][1] < 3000:
        errori.append("il video non avanza")
    righe.append(f"uscite video attive: {stato['vout']} (plugin audio/video caricati: "
                 f"{', '.join(stato.get('uscite') or []) or '-'})")
    if not stato["vout"]:
        errori.append("nessuna uscita video")
    if sys.platform.startswith("linux"):
        righe.append(f"salvaschermo inibito durante la riproduzione: {'sì' if stato['inib'] else 'no'}"
                     + ("" if os.environ.get("DBUS_SESSION_BUS_ADDRESS") or os.environ.get("XDG_RUNTIME_DIR")
                        else " (nessun bus D-Bus di sessione)"))
    if finestra:
        fs = stato["fs"]
        if fs is None:
            errori.append("schermo intero non provato")
        else:
            righe.append(f"schermo intero: {'sì' if fs[0] else 'NO'}, comandi sopra il video a tutto schermo: "
                         f"{'sì' if fs[1] else 'NO'} (schermo {fs[2]}, comandi {fs[3]})")
            if not (fs[0] and fs[1]):
                errori.append("schermo intero o comandi sovrapposti non a posto")
        im, im_fs = stato.get("immagine", 0.0), stato.get("immagine_fs", 0.0)
        righe.append(f"immagine nella finestra del video: {im:.0%} di punti colorati in finestra, "
                     f"{im_fs:.0%} a schermo intero")
        if im < 0.3 or im_fs < 0.3:
            errori.append("il video non si vede nella finestra")
    shutil.rmtree(cartella, ignore_errors=True)
    try:
        from tktv.util import app_data_dir
        if os.environ.get("TKTV_PROFILE") == "selftest":
            shutil.rmtree(app_data_dir(), ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass
    testo = ("OK" if not errori else "ERRORE: " + "; ".join(errori)) + "\n" + "\n".join(righe) + "\n"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(testo)
    print(testo, end="")
    return 0 if not errori else 1
