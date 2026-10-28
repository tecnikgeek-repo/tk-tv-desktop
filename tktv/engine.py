"""Motore video: libVLC incluso nell'app (cartella «vlc»), firmato da VideoLAN.

Gestisce HLS, DASH, MPEG-TS e lo user-agent per canale (#EXTVLCOPT della playlist).
"""
import ctypes
import glob
import os
import sys
import urllib.parse

from tktv.util import app_root

if sys.platform == "darwin":
    DEFAULT_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) tk-tv"
    LIB_NAME = os.path.join("lib", "libvlc.dylib")
else:
    DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) tk-tv"
    LIB_NAME = "libvlc.dll"

_vlc = None
_instance = None


def vlc_dir():
    """Cartella di libVLC: «vlc» nella versione installata, «vendor/vlc-x.y.z» in sviluppo.
    Su Mac le librerie stanno in vlc/lib e i plugin in vlc/plugins (come dentro VLC.app)."""
    root = app_root()
    candidates = [os.path.join(root, "vlc")] + sorted(glob.glob(os.path.join(root, "vendor", "vlc-*")), reverse=True)
    for c in candidates:
        if os.path.isfile(os.path.join(c, LIB_NAME)):
            return c
    return None


def load():
    """Importa python-vlc puntando alla libVLC inclusa. Ritorna il modulo oppure lancia RuntimeError."""
    global _vlc
    if _vlc is not None:
        return _vlc
    folder = vlc_dir()
    if folder is None:
        raise RuntimeError("Motore video non trovato: reinstalla tk-tv.")
    os.environ["PYTHON_VLC_LIB_PATH"] = os.path.join(folder, LIB_NAME)
    os.environ["PYTHON_VLC_MODULE_PATH"] = os.path.join(folder, "plugins")
    os.environ["VLC_PLUGIN_PATH"] = os.path.join(folder, "plugins")
    if sys.platform == "darwin":
        # libvlc.dylib cerca @rpath/libvlccore.dylib: caricata prima, dyld la riconosce per nome
        ctypes.CDLL(os.path.join(folder, "lib", "libvlccore.dylib"), mode=ctypes.RTLD_GLOBAL)
    else:
        try:
            os.add_dll_directory(folder)
        except (AttributeError, OSError):
            pass
    import vlc
    _vlc = vlc
    return vlc


_warm_procs = []

# Windows: i plugin che libVLC carica davvero guardando i canali (misurati su tutta la lista, 1.0.8),
# più le uscite audio/video di riserva per le altre schede video. Sono anche quelli che installer/build.ps1
# tiene nel pacchetto (più pochi altri): i plugin di DVD, Blu-ray, encoder e accessi locali non ci sono.
WIN_HOT = """adaptive adf aes3 aom araw archive asf avcodec avi caf cdg console_logger cvdsub d3d11va dav1d diracsys
direct3d11_filters direct3d11 direct3d9_filters directory_demux dmxmus drawable es faad file_logger filesystem
flacsys float_mixer fluidsynth freetype gme gnutls grey_yuv hds https i420_nv12 i420_rgb_mmx i420_rgb i420_rgb_sse2
i420_yuy2_mmx i420_yuy2 i420_yuy2_sse2 i422_i420 i422_yuy2_mmx i422_yuy2 i422_yuy2_sse2 inflate jpeg live555
lpcm memory_keystore mkv mmdevice mp4 mpc mpg123 nuv ogg opus packetizer_av1 packetizer_dirac packetizer_flac
packetizer_h264 packetizer_hevc packetizer_mlp packetizer_mpeg4audio packetizer_mpeg4video packetizer_mpegvideo playlist
png prefetch rawvideo record samplerate scaletempo skiptags smf spdif speex spudec svcdsub swscale theora ts tta ttml
vorbis wasapi wav webvtt winhibit xa xml yuvp yuy2_i420 yuy2_i422
dxva2 direct3d9 gl wgl wingdi directsound waveout""".split()
WIN_WARM_PROCS = 4  # Windows carica le DLL di un processo una alla volta: 4 processi = 4 file in parallelo


def _win_hot_files(folder):
    found = {}
    for d, _, files in os.walk(os.path.join(folder, "plugins")):
        for f in files:
            found[f.lower()] = os.path.join(d, f)
    return [os.path.join(folder, "libvlccore.dll"), os.path.join(folder, LIB_NAME)] + \
        [found[f"lib{n}_plugin.dll"] for n in WIN_HOT if f"lib{n}_plugin.dll" in found]


def warm_up_async():
    """La prima volta che un plugin di VLC viene caricato il sistema lo controlla: su Mac la firma (quasi un
    secondo l'uno), su Windows l'antivirus / Smart App Control (~0,1 s l'uno, ~100 plugin = 10 s) dopo ogni
    riavvio. All'avvio dei processi separati caricano i plugin in anticipo, mentre si sceglie il canale;
    quando sono già controllati finiscono in un attimo."""
    if vlc_dir() is None:
        return
    import subprocess
    cmd = [sys.executable, "--warm-vlc"] if getattr(sys, "frozen", False) else \
        [sys.executable, os.path.join(app_root(), "run.py"), "--warm-vlc"]
    if sys.platform == "win32":
        cmds = [cmd + [f"{i}/{WIN_WARM_PROCS}"] for i in range(WIN_WARM_PROCS)]
        flags = 0x08000000 | 0x00004000  # CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS
    else:
        cmds, flags = [cmd], 0
    for c in cmds:
        try:
            _warm_procs.append(subprocess.Popen(c, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                stderr=subprocess.DEVNULL, creationflags=flags))
        except OSError:
            pass


def warming():
    return any(p.poll() is None for p in _warm_procs)


def warm_cli():
    """--warm-vlc: carica libVLC e i plugin (processo separato, poi esce)."""
    folder = vlc_dir()
    if folder is None:
        return 1
    if sys.platform == "win32":
        # «i/n»: questo processo prende un file ogni n a partire dall'i-esimo
        part = next((a for a in sys.argv if "/" in a and a.replace("/", "").isdigit()), "0/1")
        i, n = (int(x) for x in part.split("/"))
        k32 = ctypes.WinDLL("kernel32")
        k32.LoadLibraryExW.restype = ctypes.c_void_p
        k32.LoadLibraryExW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint32]
        k32.FreeLibrary.argtypes = [ctypes.c_void_p]
        for path in _win_hot_files(folder)[i::n]:
            # DONT_RESOLVE_DLL_REFERENCES: la DLL viene mappata (e quindi controllata) senza eseguirne il codice
            h = k32.LoadLibraryExW(path, None, 0x00000001)
            if h:
                k32.FreeLibrary(h)
        return 0
    ctypes.CDLL(os.path.join(folder, "lib", "libvlccore.dylib"), mode=ctypes.RTLD_GLOBAL)
    ctypes.CDLL(os.path.join(folder, LIB_NAME))
    # prima i plugin che servono a ogni canale, poi gli altri
    first = ("adaptive", "ts", "es", "avcodec", "videotoolbox", "faad", "https", "http", "gnutls", "caopengllayer",
             "vout_macosx", "auhal", "mp4", "playlist", "logger")
    plugins = sorted(glob.glob(os.path.join(folder, "plugins", "*.dylib")),
                     key=lambda p: not any(os.path.basename(p).startswith(f"lib{f}_") for f in first))
    for path in plugins:
        try:
            ctypes.CDLL(path, mode=ctypes.RTLD_LOCAL)
        except OSError:
            pass
    return 0


def instance():
    global _instance
    if _instance is None:
        vlc = load()
        _instance = vlc.Instance([
            "--no-video-title-show", "--no-osd", "--no-snapshot-preview", "--no-stats",
            "--quiet", "--no-lua", "--ignore-config", "--no-media-library",
            "--network-caching=2000", "--adaptive-logic=highest",
        ])
        if _instance is None:
            raise RuntimeError("Impossibile avviare il motore video.")
        _instance.set_user_agent("tk-tv", DEFAULT_UA)
    return _instance


def is_dash(channel):
    # come su Android: «.mpd» nell'URL = DASH
    return ".mpd" in channel.url.lower()


def media_options(channel):
    return [f":http-user-agent={channel.user_agent or DEFAULT_UA}", ":http-reconnect", ":network-caching=2000"]


def needs_dashfix(channel):
    """DASH generato da uno script (indirizzo con «.mpd» solo nei parametri): è lì che arrivano tipo
    sbagliato e BaseURL per Representation. I file .mpd veri VLC li legge da solo: meglio non toccarli."""
    path = urllib.parse.urlparse(channel.url).path.lower()
    return is_dash(channel) and not path.endswith(".mpd")


def media_url(channel):
    from tktv.playlist import schema_ammesso
    if not schema_ammesso(channel.url):
        # solo flussi di rete: mai file locali, cartelle condivise, webcam o schermo (vedi playlist.SCHEMI_FLUSSO)
        raise RuntimeError("Indirizzo del canale non supportato: tk-tv apre solo flussi http, https, udp, rtp, "
                           "rtsp e rtmp.")
    if needs_dashfix(channel) and channel.url.lower().startswith(("http://", "https://")):
        # manifest DASH serviti con il tipo sbagliato: vanno corretti prima di darli a VLC 3 (vedi dashfix)
        from tktv import dashfix
        return dashfix.local_url(channel.url, channel.user_agent or DEFAULT_UA)
    return channel.url


def make_media(channel, inst=None):
    vlc = load()
    media = (inst or instance()).media_new(media_url(channel))
    for opt in media_options(channel):
        media.add_option(opt)
    return media, vlc
