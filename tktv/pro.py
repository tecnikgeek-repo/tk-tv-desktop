"""Licenza, benvenuto e donazione di tk-tv.

tk-tv è software libero (AGPL-3.0) con tutte le funzioni per tutti: niente chiavi, niente Pro.
Qui restano la libreria comune (statistiche solo col consenso), la finestra di benvenuto,
le licenze dei componenti e l'invito discreto a offrire un caffè.
"""
from PySide6.QtWidgets import QApplication

from tktv import APP_TITLE, URL_SORGENTE, VERSION
from tktv.util import resource_path

DONAZIONE = "https://pietrodefilippis.it/donazione/"


def crea_licenza(versione):
    """La licenza sta nella cartella dati dell'utente (i test usano un profilo a parte)."""
    try:
        import os
        from tktv.tk_licenza import Licenza
        from tktv.util import app_data_dir
        return Licenza("tk-tv", versione, os.path.join(app_data_dir(), "licenza"))
    except Exception:
        return None


def licenza():
    return getattr(QApplication.instance(), "licenza", None)


def donazione():
    lic = licenza()
    try:
        return lic.info()["donazione"] if lic is not None else DONAZIONE
    except Exception:
        return DONAZIONE


def _logo():
    from tktv.icon import badge_pixmap
    return badge_pixmap(64, 18)


def cartella_licenze():
    """Cartella «licenze» del pacchetto (accanto a run.py su Windows, nelle risorse dell'app su Mac)."""
    return resource_path("licenze")


def benvenuto(parent=None):
    """Prima apertura: software libero, nessuna garanzia, privacy e consenso alle statistiche (una volta sola)."""
    try:
        from tktv.tk_licenza_qt import benvenuto as mostra
        mostra(licenza(), APP_TITLE, URL_SORGENTE, parent=parent, logo=_logo(), righe_extra=(
            "Il link della tua lista resta solo su questo computer. In rete tk-tv contatta gli indirizzi "
            "della tua lista (canali e loghi), Google, DuckDuckGo e Twitch per le icone di «App e pay TV» "
            "e pietrodefilippis.it per controllare gli aggiornamenti.",))
    except Exception:
        pass


def mostra_licenze(parent=None):
    from tktv.tk_licenza_qt import LicenzeDialog
    LicenzeDialog(APP_TITLE, VERSION, URL_SORGENTE, cartella_licenze(), parent).exec()


def casella_statistiche():
    from tktv.tk_licenza_qt import casella_statistiche as crea
    return crea(licenza())


def invito(parent=None, puo_mostrare=None):
    """Invito al caffè all'avvio: la prima volta e poi al massimo una volta al mese (vedi tk_licenza_qt)."""
    try:
        from tktv.tk_licenza_qt import invito_caffe
        invito_caffe(licenza(), APP_TITLE, parent, _logo(), puo_mostrare)
    except Exception:
        pass
