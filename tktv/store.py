"""Preferenze salvate (registro utente di Windows, via QSettings)."""
from PySide6.QtCore import QSettings

from tktv.util import profile_name


class Store:
    def __init__(self):
        self.settings = QSettings("TecnikGeek", profile_name())

    # --- playlist
    @property
    def playlist_url(self):
        return self.settings.value("playlist_url", "", type=str)

    @playlist_url.setter
    def playlist_url(self, value):
        self.settings.setValue("playlist_url", value.strip())

    # --- preferiti (per nome canale, come su Android)
    @property
    def favorites(self):
        value = self.settings.value("favorites", [])
        if isinstance(value, str):
            value = [value] if value else []
        return set(value or [])

    def toggle_favorite(self, name):
        favs = self.favorites
        if name in favs:
            favs.remove(name)
        else:
            favs.add(name)
        self.settings.setValue("favorites", sorted(favs))
        return favs

    # --- audio
    @property
    def volume(self):
        return self.settings.value("volume", 80, type=int)

    @volume.setter
    def volume(self, value):
        self.settings.setValue("volume", int(value))

    # --- ultimo canale guardato e «riparti da lì all'avvio»
    @property
    def last_channel(self):
        return self.settings.value("last_channel", "", type=str)

    @last_channel.setter
    def last_channel(self, value):
        self.settings.setValue("last_channel", value)

    @property
    def resume_last(self):
        return self.settings.value("resume_last", False, type=bool)

    @resume_last.setter
    def resume_last(self, value):
        self.settings.setValue("resume_last", bool(value))

    # --- ultima sezione aperta nella lista
    @property
    def last_section(self):
        return self.settings.value("last_section", "", type=str)

    @last_section.setter
    def last_section(self, value):
        self.settings.setValue("last_section", value)
