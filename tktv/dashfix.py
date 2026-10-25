"""Correzione dei manifest DASH per libVLC 3.

Alcuni server generano il manifest DASH con uno script e lo servono in modo che ExoPlayer (Android)
tollera e VLC 3 no:
1. con un «Content-Type» sbagliato (es. «video/MP2T») → VLC non lo riconosce come DASH;
2. con il percorso dei segmenti nel <BaseURL> della <Representation> mentre il <SegmentTemplate> è
   nell'<AdaptationSet>: VLC 3 ignora quel BaseURL e chiede i segmenti nella cartella sbagliata (404).

Un piccolo server locale (solo 127.0.0.1) scarica il manifest con lo user-agent del canale, sposta il
BaseURL della Representation dentro media/initialization del SegmentTemplate e lo passa a VLC con il
tipo giusto. I manifest live si aggiornano ogni pochi secondi: VLC li richiede di nuovo e il server
li riscarica e corregge ogni volta.

Il server risponde solo agli indirizzi che contengono il suo codice casuale (creato a ogni avvio):
un altro programma o una pagina web aperta sul computer non può usarlo per scaricare altro.
"""
import hmac
import http.server
import re
import secrets
import threading
import urllib.parse
import urllib.request

from tktv.playlist import _ssl_context

MAX_MANIFEST = 8 * 1024 * 1024  # un manifest DASH è di pochi KB: oltre non è un manifest

_server = None
_token = secrets.token_urlsafe(24)
_lock = threading.Lock()


def absolute_base(text, source_url):
    """Il manifest arriva a VLC da 127.0.0.1: i percorsi relativi vanno ancorati al server originale."""
    m = re.search(r"<MPD\b[^>]*>(\s*(?:<ProgramInformation\b.*?</ProgramInformation>\s*)?)<BaseURL>\s*(.*?)\s*</BaseURL>",
                  text, flags=re.S)
    if m:
        absolute = urllib.parse.urljoin(source_url, m.group(2))
        return text[:m.start(2)] + absolute + text[m.end(2):]
    folder = urllib.parse.urljoin(source_url, ".")
    return re.sub(r"(<MPD\b[^>]*>)", lambda mm: f"{mm.group(1)}\n<BaseURL>{folder}</BaseURL>", text, count=1, flags=re.S)


def rewrite_mpd(text, source_url=""):
    if source_url:
        text = absolute_base(text, source_url)

    def fix_set(m):
        block = m.group(0)
        reps = re.findall(r"<Representation\b.*?</Representation>", block, flags=re.S)
        found = [re.search(r"<BaseURL>\s*(.*?)\s*</BaseURL>", r, flags=re.S) for r in reps]
        bases = {f.group(1) for f in found if f}
        # solo il caso sicuro: SegmentTemplate comune e la stessa BaseURL relativa in tutte le Representation
        if not reps or not all(found) or len(bases) != 1 or "<SegmentTemplate" not in block:
            return block
        base = bases.pop()
        if re.match(r"^[a-z]+://", base, flags=re.I):
            return block
        block = re.sub(r"(<Representation\b.*?)\s*<BaseURL>.*?</BaseURL>", r"\1", block, flags=re.S)

        def prefix(attr):
            return lambda mm: f'{attr}="{base}{mm.group(1)}"'

        block = re.sub(r'\bmedia="([^"]*)"', prefix("media"), block)
        block = re.sub(r'\binitialization="([^"]*)"', prefix("initialization"), block)
        return block

    return re.sub(r"<AdaptationSet\b.*?</AdaptationSet>", fix_set, text, flags=re.S)


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parts = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(parts.query)
        # senza il codice giusto nessuna risposta utile (confronto a tempo costante)
        if not hmac.compare_digest(q.get("k", [""])[0].encode(), _token.encode()):
            self.send_error(403)
            return
        url, ua = q.get("u", [""])[0], q.get("ua", [""])[0]
        if not url.lower().startswith(("http://", "https://")):
            self.send_error(400)
            return
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua or "tk-tv"})
            ctx = _ssl_context() if url.lower().startswith("https") else None
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                final_url = resp.geturl()  # dopo eventuali redirect
                if not final_url.lower().startswith(("http://", "https://")):
                    raise ValueError("redirect non ammesso")
                text = resp.read(MAX_MANIFEST + 1).decode("utf-8", errors="replace")
            if len(text) > MAX_MANIFEST:
                raise ValueError("manifest troppo grande")
        except Exception:
            self.send_error(502)
            return
        body = (rewrite_mpd(text, final_url) if "<MPD" in text else text).encode("utf-8")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/dash+xml")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        except ConnectionError:
            pass  # VLC ha chiuso la richiesta (canale cambiato o player fermato): normale

    def log_message(self, *args):
        pass


def local_url(url, user_agent):
    """URL locale da dare a VLC al posto del manifest originale."""
    global _server
    with _lock:
        if _server is None:
            _server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
            _server.daemon_threads = True
            threading.Thread(target=_server.serve_forever, daemon=True).start()
    q = urllib.parse.urlencode({"k": _token, "u": url, "ua": user_agent})
    return f"http://127.0.0.1:{_server.server_port}/manifest.mpd?{q}"
