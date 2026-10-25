"""Verifica che la libVLC del pacchetto (plugin ridotti) apra ancora i flussi: http, HLS, DASH (anche col tipo
sbagliato, attraverso il proxy locale), UDP e RTP. Tutto in locale (127.0.0.1), niente internet; serve ffmpeg.

Uso: python tests/probe_flussi.py [cartella_vlc]
     cartella_vlc = la cartella «vlc» del pacchetto estratto (predefinita: vendor/vlc-x.y.z di sviluppo)
"""
import http.server
import os
import shutil
import site
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
site.addsitedir(os.path.join(ROOT, ".venv", "Lib", "site-packages"))
sys.path.insert(0, ROOT)

from tktv import engine  # noqa: E402
from tktv.playlist import Channel  # noqa: E402

if len(sys.argv) > 1:
    cartella = os.path.abspath(sys.argv[1])
    engine.vlc_dir = lambda: cartella

FFMPEG = shutil.which("ffmpeg")
if not FFMPEG:
    sys.exit("Serve ffmpeg nel PATH per creare i video di prova.")

tmp = tempfile.mkdtemp(prefix="tktv-flussi-")
src = os.path.join(tmp, "prova.ts")
base = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
gen = ["-f", "lavfi", "-i", "testsrc=size=640x360:rate=25", "-f", "lavfi", "-i", "sine=frequency=440",
       "-t", "12", "-c:v", "libx264", "-preset", "ultrafast", "-g", "25", "-pix_fmt", "yuv420p", "-c:a", "aac"]
subprocess.run(base + gen + [src], check=True)
os.makedirs(os.path.join(tmp, "hls"))
subprocess.run(base + ["-i", src, "-c", "copy", "-f", "hls", "-hls_time", "2", "-hls_list_size", "0",
                       os.path.join(tmp, "hls", "index.m3u8")], check=True)
os.makedirs(os.path.join(tmp, "dash"))
# ffmpeg scrive i segmenti DASH nella cartella corrente: si lancia dentro quella del manifest
subprocess.run(base + gen + ["-f", "dash", "-seg_duration", "2", "manifest.mpd"], check=True,
               cwd=os.path.join(tmp, "dash"))


class Server(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=tmp, **k)

    def do_GET(self):
        if self.path.startswith("/dash/script"):
            # DASH «generato da uno script»: niente .mpd nel percorso e tipo sbagliato (caso del proxy dashfix)
            body = open(os.path.join(tmp, "dash", "manifest.mpd"), "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "video/MP2T")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Server)
threading.Thread(target=srv.serve_forever, daemon=True).start()
http_base = f"http://127.0.0.1:{srv.server_port}"


def porta_libera():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def invia_udp(porta, fermo):
    data = open(src, "rb").read()
    pacchetto = 188 * 7
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        while not fermo.is_set():
            for i in range(0, len(data), pacchetto):
                if fermo.is_set():
                    break
                s.sendto(data[i:i + pacchetto], ("127.0.0.1", porta))
                time.sleep(0.0015)


vlc = engine.load()
print("libVLC:", vlc.libvlc_get_version().decode(), "da", engine.vlc_dir())
inst = vlc.Instance(["--quiet", "--no-lua", "--ignore-config", "--vout=dummy", "--aout=dummy",
                     "--network-caching=1000"])
risultati = []


def prova(nome, url, prima=None, dopo=None):
    extra = prima() if prima else None
    ch = Channel(1, nome, "", url, "", "")
    mp = inst.media_player_new()
    m, _ = engine.make_media(ch, inst)  # stesse opzioni dell'app (e proxy DASH quando serve)
    mp.set_media(m)
    mp.play()
    t0 = time.time()
    size = (0, 0)
    while time.time() - t0 < 20:
        st = mp.get_state()
        size = mp.video_get_size(0) or (0, 0)
        if st == vlc.State.Error or (st == vlc.State.Playing and size[0] > 0):
            break
        time.sleep(0.3)
    ok = size[0] > 0
    print(f"{'OK ' if ok else 'NO '} {nome}: {mp.get_state()} video={size[0]}x{size[1]} in {time.time() - t0:.1f}s")
    mp.stop()
    mp.release()
    if dopo:
        dopo(extra)
    risultati.append(ok)


prova("http (MPEG-TS)", f"{http_base}/prova.ts")
prova("HLS", f"{http_base}/hls/index.m3u8")
prova("DASH", f"{http_base}/dash/manifest.mpd")
prova("DASH tipo sbagliato (proxy)", f"{http_base}/dash/script?canale=1&ext=.mpd")

p_udp = porta_libera()
fermo_udp = threading.Event()
prova("UDP", f"udp://@127.0.0.1:{p_udp}",
      prima=lambda: threading.Thread(target=invia_udp, args=(p_udp, fermo_udp), daemon=True).start(),
      dopo=lambda _x: fermo_udp.set())

p_rtp = porta_libera()
prova("RTP", f"rtp://@127.0.0.1:{p_rtp}",
      prima=lambda: subprocess.Popen(base + ["-re", "-stream_loop", "-1", "-i", src, "-c", "copy", "-f", "rtp_mpegts",
                                             f"rtp://127.0.0.1:{p_rtp}"]),
      dopo=lambda proc: proc.terminate())

# RTSP: serve un server RTSP; qui si controlla solo che il modulo (live555) sia nel pacchetto
plug = os.path.join(engine.vlc_dir(), "plugins", "access", "liblive555_plugin.dll")
if sys.platform == "win32":
    print(("OK " if os.path.isfile(plug) else "NO ") + " RTSP: modulo live555 " +
          ("presente" if os.path.isfile(plug) else "MANCANTE"))
    risultati.append(os.path.isfile(plug))

srv.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
print("TUTTO OK" if all(risultati) else "QUALCOSA NON VA")
sys.exit(0 if all(risultati) else 1)
