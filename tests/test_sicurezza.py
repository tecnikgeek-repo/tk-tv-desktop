"""Prove senza rete e senza finestre: schemi ammessi dalla lista, loghi, proxy DASH locale col codice.

Uso: python -m unittest tests.test_sicurezza   (dalla cartella del progetto)
"""
import http.server
import os
import site
import sys
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
site.addsitedir(os.path.join(ROOT, ".venv", "Lib", "site-packages"))
sys.path.insert(0, ROOT)
os.environ["TKTV_PROFILE"] = "test"  # mai le impostazioni reali

from tktv import dashfix, engine, playlist  # noqa: E402

LISTA = """#EXTM3U
#EXTINF:-1 tvg-chno="1" tvg-logo="https://esempio.test/logo1.png" group-title="Generali",Canale Uno
https://esempio.test/uno.m3u8
#EXTINF:-1 tvg-logo="file:///C:/Windows/win.ini",Canale Due
http://esempio.test/due.ts
#EXTINF:-1,Multicast
udp://@239.0.0.1:1234
#EXTINF:-1,RTSP
rtsp://esempio.test/live
#EXTINF:-1,RTP
rtp://@239.0.0.2:5004
#EXTINF:-1,RTMP
rtmp://esempio.test/live/canale
#EXTINF:-1,File locale
file:///C:/Users/Public/video.mp4
#EXTINF:-1,Percorso
C:\\Users\\Public\\video.mp4
#EXTINF:-1,Condivisa
smb://server/cartella/video.mkv
#EXTINF:-1,Webcam
dshow://
#EXTINF:-1,Schermo
screen://
"""

MPD = """<?xml version="1.0"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="dynamic">
<Period>
<AdaptationSet mimeType="video/mp4">
<SegmentTemplate media="seg-$Number$.m4s" initialization="init.mp4"/>
<Representation id="v1" bandwidth="1000"><BaseURL>video/</BaseURL></Representation>
<Representation id="v2" bandwidth="2000"><BaseURL>video/</BaseURL></Representation>
</AdaptationSet>
</Period>
</MPD>"""


class Lista(unittest.TestCase):
    def test_solo_flussi_di_rete(self):
        nomi = [c.name for c in playlist.parse(LISTA)]
        self.assertEqual(nomi, ["Canale Uno", "Canale Due", "Multicast", "RTSP", "RTP", "RTMP"])

    def test_loghi_solo_web(self):
        canali = {c.name: c for c in playlist.parse(LISTA)}
        self.assertEqual(canali["Canale Uno"].logo, "https://esempio.test/logo1.png")
        self.assertEqual(canali["Canale Due"].logo, "")

    def test_motore_rifiuta_altri_schemi(self):
        for url in ("file:///C:/Windows/win.ini", "smb://server/x", "dshow://", "screen://", "C:\\video.mp4"):
            ch = playlist.Channel(1, "x", "", url, "", "")
            with self.assertRaises(RuntimeError):
                engine.media_url(ch)
        ch = playlist.Channel(1, "x", "", "https://esempio.test/uno.m3u8", "", "")
        self.assertEqual(engine.media_url(ch), ch.url)


class _Origine(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = MPD.encode()
        self.send_response(200)
        self.send_header("Content-Type", "video/MP2T")  # tipo sbagliato, come certi server
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class ProxyDash(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Origine)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.origine = f"http://127.0.0.1:{cls.srv.server_port}/live/manifest?ext=.mpd"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_riscrittura(self):
        out = dashfix.rewrite_mpd(MPD, "http://esempio.test/live/manifest?ext=.mpd")
        self.assertIn('media="video/seg-$Number$.m4s"', out)
        self.assertIn('initialization="video/init.mp4"', out)
        self.assertIn("<BaseURL>http://esempio.test/live/</BaseURL>", out)
        self.assertNotIn("<BaseURL>video/</BaseURL>", out)

    def test_con_codice(self):
        locale = dashfix.local_url(self.origine, "tk-tv")
        with urllib.request.urlopen(locale, timeout=10) as r:
            self.assertEqual(r.headers["Content-Type"], "application/dash+xml")
            self.assertIn('media="video/seg-$Number$.m4s"', r.read().decode())

    def test_senza_codice(self):
        locale = dashfix.local_url(self.origine, "tk-tv")
        parti = urllib.parse.urlsplit(locale)
        q = urllib.parse.parse_qs(parti.query)
        for k in ("", "sbagliato"):
            q2 = dict(q, k=[k]) if k else {x: v for x, v in q.items() if x != "k"}
            url = urllib.parse.urlunsplit(parti._replace(query=urllib.parse.urlencode(q2, doseq=True)))
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(url, timeout=10)
            self.assertEqual(e.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
