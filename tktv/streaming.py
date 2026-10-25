"""Pay TV e piattaforme on demand: su Windows si aprono i siti ufficiali nel browser.

Come su Android, riprodurre questi contenuti dentro tk-tv è impossibile (DRM Widevine,
nessuna API pubblica): si può solo aprire il servizio ufficiale.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AppStreaming:
    nome: str
    url: str
    colore: str
    sigla: str        # mostrata nel riquadro colorato finché il logo non è scaricato (o se non arriva)
    icona: str = ""   # link del logo quando quello di Google è piccolo o sgranato

    @property
    def logo(self):
        if self.icona:
            return self.icona
        host = self.url.split("/")[2]
        return f"https://www.google.com/s2/favicons?domain={host}&sz=256"


CATALOGO = [
    AppStreaming("Netflix", "https://www.netflix.com/browse", "#e50914", "N"),
    AppStreaming("Prime Video", "https://www.primevideo.com", "#1a98ff", "P"),
    AppStreaming("Disney+", "https://www.disneyplus.com", "#113ccf", "D+"),
    AppStreaming("HBO Max", "https://www.hbomax.com", "#5b2ee5", "HBO"),
    AppStreaming("NOW", "https://www.nowtv.it", "#00c2a8", "NOW"),
    AppStreaming("Sky Go", "https://skygo.sky.it", "#0a5cd6", "SKY"),
    AppStreaming("DAZN", "https://www.dazn.com/it-IT/home", "#f7ff1a", "DAZN"),
    AppStreaming("Apple TV", "https://tv.apple.com/it", "#1d1d1f", "tv"),
    AppStreaming("Paramount+", "https://www.paramountplus.com/it/", "#0064ff", "P+",
                 "https://icons.duckduckgo.com/ip3/www.paramountplus.com.ico"),
    AppStreaming("discovery+", "https://www.discoveryplus.com/it", "#2175d9", "d+"),
    AppStreaming("RaiPlay", "https://www.raiplay.it", "#0a3d91", "Rai"),
    AppStreaming("Mediaset Infinity", "https://mediasetinfinity.mediaset.it", "#0047ab", "M∞"),
    AppStreaming("YouTube", "https://www.youtube.com", "#ff0000", "▶"),
    AppStreaming("Twitch", "https://www.twitch.tv", "#9146ff", "T", "https://www.twitch.tv/apple-touch-icon.png"),
    AppStreaming("Plex", "https://app.plex.tv", "#e5a00d", "PLEX"),
]
