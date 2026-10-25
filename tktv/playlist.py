"""Playlist M3U: modello del canale, parsing, download e copia locale (stessa logica dell'app Android)."""
import os
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass

from tktv.util import app_data_dir

# indirizzi dei canali che tk-tv passa a VLC: solo flussi di rete. Niente file://, smb://, dshow://, screen://…
# (una lista scaricata da internet non deve poter aprire file, cartelle condivise, webcam o lo schermo del computer)
SCHEMI_FLUSSO = ("http", "https", "udp", "rtp", "rtsp", "rtmp")
SCHEMI_LOGO = ("http", "https")

# Canali "generalisti" da mostrare in evidenza, in quest'ordine.
GENERALISTI = ["rai1", "rai2", "rai3", "rete4", "canale5", "italia1", "la7", "tv8", "nove"]


@dataclass(frozen=True)
class Channel:
    number: int
    name: str
    group: str
    url: str
    user_agent: str
    logo: str


_RE_CHNO = re.compile(r'tvg-chno="([^"]*)"')
_RE_GROUP = re.compile(r'group-title="([^"]*)"')
_RE_LOGO = re.compile(r'tvg-logo="([^"]*)"')
_RE_NUM_NAME = re.compile(r"^\[(\d+)]\s*(.+)$")


def schema_ammesso(url, schemi=SCHEMI_FLUSSO):
    """Vero se l'indirizzo inizia con uno degli schemi ammessi (es. «https://», «udp://@239.0.0.1:1234»)."""
    m = re.match(r"^([a-z][a-z0-9+.-]*)://", (url or "").strip(), flags=re.I)
    return bool(m) and m.group(1).lower() in schemi


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse(text):
    """Analizza il testo di una playlist M3U e ritorna la lista dei canali."""
    channels = []
    number, name, group, logo, ua = 0, "", "", "", ""
    auto = 1000
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#EXTM3U"):
            continue
        if line.startswith("#EXTINF"):
            number, name, group, logo, ua = 0, "", "", "", ""
            m = _RE_CHNO.search(line)
            if m:
                number = _to_int(m.group(1))
            m = _RE_GROUP.search(line)
            if m:
                group = m.group(1)
            m = _RE_LOGO.search(line)
            if m and schema_ammesso(m.group(1), SCHEMI_LOGO):
                logo = m.group(1)
            label = line.rsplit(",", 1)[-1].strip()
            m = _RE_NUM_NAME.match(label)
            if m:
                number = _to_int(m.group(1), number)
                name = m.group(2).strip()
            else:
                name = label
            if number == 0:
                number = auto
                auto += 1
        elif line.startswith("#EXTVLCOPT:http-user-agent="):
            ua = line.split("=", 1)[1].strip()
        elif line.startswith("#"):
            continue
        elif schema_ammesso(line):
            channels.append(Channel(number, name, group, line, ua, logo))
        # le altre righe (file locali, smb://, dshow://, screen://…) si ignorano: non sono canali TV
    return channels


def generalist_rank(name):
    """Posizione del canale tra i generalisti (0 = primo) oppure -1 se non lo è."""
    n = name.lower()
    for word, digit in (("uno", "1"), ("due", "2"), ("tre", "3"), ("quattro", "4"), ("cinque", "5")):
        n = n.replace(word, digit)
    n = re.sub(r"[^a-z0-9]", "", n)
    n = re.sub(r"(fhd|uhd|hd|4k)+$", "", n)
    for i, key in enumerate(GENERALISTI):
        if n == key or (n.endswith(key) and len(n) - len(key) <= 3):
            return i
    return -1


def generalisti(channels):
    ranked = sorted(((generalist_rank(c.name), c) for c in channels), key=lambda t: t[0])
    seen, out = set(), []
    for rank, ch in ranked:
        if rank >= 0 and ch.name not in seen:
            seen.add(ch.name)
            out.append(ch)
    return out


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def download(url):
    """Scarica la playlist (link http/https oppure file sul PC). Lancia un'eccezione con testo in italiano."""
    url = url.strip()
    if os.path.isfile(url):
        with open(url, "rb") as fh:
            data = fh.read()
    else:
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError("Il link deve iniziare con http:// o https://")
        req = urllib.request.Request(url, headers={"User-Agent": "tk-tv"})
        try:
            ctx = _ssl_context() if url.lower().startswith("https") else None
            with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
                data = resp.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Errore HTTP {exc.code}") from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Server non raggiungibile ({exc.reason})") from None
        except TimeoutError:
            raise RuntimeError("Il server non risponde (tempo scaduto)") from None
    text = data.decode("utf-8-sig", errors="replace")
    channels = parse(text)
    if not channels:
        raise RuntimeError("Nessun canale trovato nella playlist")
    return text, channels


# ---------------------------------------------------------------- copia locale (avvio immediato e offline)
def _cache_file():
    return os.path.join(app_data_dir(), "playlist.m3u")


def save_cache(text):
    try:
        with open(_cache_file(), "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError:
        pass


def load_cache():
    try:
        with open(_cache_file(), encoding="utf-8") as fh:
            return parse(fh.read())
    except OSError:
        return []
