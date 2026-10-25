"""Installazione da ZIP (senza exe dedicati): avviata da «Installa tk-tv.cmd» con il Python incluso.

Evita i blocchi di antivirus (Avast CyberCapture) e Smart App Control sugli exe non firmati.
"""
import ctypes
import os
import shutil
import subprocess
import threading
import time
from ctypes import POINTER, byref, c_void_p, wintypes

from tktv import APP_TITLE, VERSION
from tktv.uninstall import LEGACY_SHORTCUTS, SHORTCUT, UNINSTALL_KEY

ITEMS = ["python", "tktv", "assets", "vlc", "licenze", "run.py"]
# copia di pythonw.exe con il nome dell'app (in Gestione attività si vede tk-tv.exe). È lo stesso file, quindi
# Smart App Control lo riconosce come pythonw.exe. pythonw.exe resta nei pacchetti (lo cercano gli aggiornamenti
# dalle versioni ≤ 1.0.8) ma la copia installata lo cancella appena l'app gira come tk-tv.exe (cleanup_launchers).
EXE_NAME = "tk-tv.exe"
# alzare quando cambia dove puntano collegamenti e disinstallazione: al prossimo avvio l'app li rifà tutti
LAUNCH_SCHEMA = "4"  # 2: tk-tv.exe · 3: «tkTV.lnk» al posto di «TK TV.lnk» · 4: «tk-tv.lnk» al posto di entrambi
TASKBAR_PINS =os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar")


# ---------------------------------------------------------------- percorsi
def source_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_dest():
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Programs", "tk-tv-player")


def existing_dest():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
            path = winreg.QueryValueEx(k, "InstallLocation")[0]
            return path if path and os.path.isdir(path) else None
    except OSError:
        return None


def special_folder(csidl):
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf)
    return buf.value


# ---------------------------------------------------------------- collegamenti (IShellLinkW via ctypes)
class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]

    def __init__(self, text):
        super().__init__()
        ctypes.oledll.ole32.CLSIDFromString(text, byref(self))


def _vcall(ptr, index, restype, *args):
    """Chiama il metodo n. `index` della vtable di un'interfaccia COM."""
    vtable = ctypes.cast(ptr, POINTER(POINTER(c_void_p))).contents
    argtypes = [c_void_p]
    for a in args:
        if isinstance(a, str):
            argtypes.append(wintypes.LPCWSTR)
        elif isinstance(a, ctypes._SimpleCData):
            argtypes.append(type(a))
        else:  # byref(...) e puntatori
            argtypes.append(c_void_p)
    fn = ctypes.WINFUNCTYPE(restype, *argtypes)(vtable[index])
    return fn(ptr, *args)


def create_shortcut(path, target, arguments, workdir, icon, description):
    ole32 = ctypes.oledll.ole32
    ole32.CoInitialize(None)
    link = c_void_p()
    ole32.CoCreateInstance(byref(GUID("{00021401-0000-0000-C000-000000000046}")), None, 1,
                           byref(GUID("{000214F9-0000-0000-C000-000000000046}")), byref(link))
    # indici vtable IShellLinkW: SetDescription 7, SetWorkingDirectory 9, SetArguments 11, SetIconLocation 17, SetPath 20
    _vcall(link, 20, ctypes.HRESULT, target)
    _vcall(link, 11, ctypes.HRESULT, arguments)
    _vcall(link, 9, ctypes.HRESULT, workdir)
    _vcall(link, 17, ctypes.HRESULT, icon, ctypes.c_int(0))
    _vcall(link, 7, ctypes.HRESULT, description)
    persist = c_void_p()
    _vcall(link, 0, ctypes.HRESULT, byref(GUID("{0000010B-0000-0000-C000-000000000046}")), byref(persist))
    _vcall(persist, 6, ctypes.HRESULT, path, wintypes.BOOL(True))  # IPersistFile::Save
    _vcall(persist, 2, wintypes.ULONG)
    _vcall(link, 2, wintypes.ULONG)


# ---------------------------------------------------------------- installazione
def install(dest, desktop=True, progress=None):
    report = progress or (lambda p, s: None)
    src = source_root()
    same = os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(dest))

    report(3, "Chiusura di tk-tv se aperto…")
    if os.path.isdir(dest) and not same:
        from tktv.uninstall import kill_other_instances
        kill_other_instances(dest)
        time.sleep(0.8)

    if not same:
        files = []
        for item in ITEMS:
            p = os.path.join(src, item)
            if os.path.isdir(p):
                files += [os.path.join(d, f) for d, _, fs in os.walk(p) for f in fs]
            elif os.path.isfile(p):
                files.append(p)
        total = len(files)
        staging = dest + ".nuova"
        if os.path.isdir(staging):
            shutil.rmtree(staging, ignore_errors=True)
        os.makedirs(staging, exist_ok=True)
        for done, f in enumerate(files, 1):
            target = os.path.join(staging, os.path.relpath(f, src))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(f, target)
            if done % 40 == 0 or done == total:
                report(5 + done * 80 // total, f"Copia dei file… {done * 100 // total}%")

        # i file estratti da uno ZIP scaricato hanno il «marchio del web»: lo si toglie per evitare avvisi a ogni avvio
        for d, _, fs in os.walk(staging):
            for name in fs:
                try:
                    os.remove(os.path.join(d, name) + ":Zone.Identifier")
                except OSError:
                    pass

        report(86, "Sostituzione della versione precedente…")
        old = dest + ".vecchia"
        if os.path.isdir(old):
            shutil.rmtree(old, ignore_errors=True)
        if os.path.isdir(dest):
            for attempt in range(30):
                try:
                    os.rename(dest, old)
                    break
                except OSError:
                    if attempt == 29:
                        raise PermissionError("tk-tv è ancora aperto: chiudilo e riprova.")
                    time.sleep(1)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        os.rename(staging, dest)
        shutil.rmtree(old, ignore_errors=True)

    report(92, "Creazione dei collegamenti…")
    register(dest, desktop)
    report(100, "Installazione completata")
    return dest


def app_exe(dest):
    exe = os.path.join(dest, "python", EXE_NAME)
    return exe if os.path.isfile(exe) else os.path.join(dest, "python", "pythonw.exe")


def has_desktop_shortcut():
    desk = special_folder(0x0010)
    return any(os.path.exists(os.path.join(desk, n)) for n in (SHORTCUT,) + LEGACY_SHORTCUTS)


def register(dest, desktop):
    """Collegamenti (menu Start e, se richiesto, desktop) e voce in «App installate»."""
    exe = app_exe(dest)
    run_py = os.path.join(dest, "run.py")
    icon = os.path.join(dest, "assets", "tk-tv.ico")
    args = f'"{run_py}"'
    description = "tk-tv - la TV in diretta della tua playlist M3U"
    for folder in (special_folder(0x0002), special_folder(0x0010)):
        for old in LEGACY_SHORTCUTS:  # «TK TV.lnk» (≤ 1.0.12) e «tkTV.lnk» (1.0.13–1.0.14) → sostituiti da «tk-tv.lnk»
            try:
                os.remove(os.path.join(folder, old))
            except OSError:
                pass
    create_shortcut(os.path.join(special_folder(0x0002), SHORTCUT), exe, args, dest, icon, description)
    if desktop:
        create_shortcut(os.path.join(special_folder(0x0010), SHORTCUT), exe, args, dest, icon, description)
    # tk-tv aggiunto alla barra delle applicazioni: è una copia a parte. Il file non si rinomina (si perderebbe il
    # fissaggio): se ne aggiorna solo la destinazione
    for name in (SHORTCUT,) + LEGACY_SHORTCUTS:
        pin = os.path.join(TASKBAR_PINS, name)
        if os.path.exists(pin):
            create_shortcut(pin, exe, args, dest, icon, description)

    import winreg
    size_kb = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(dest) for f in fs) // 1024
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
        try:
            installed_on = winreg.QueryValueEx(k, "InstallDate")[0]
        except OSError:
            installed_on = time.strftime("%Y%m%d")
        for name, value in (("DisplayName", APP_TITLE), ("DisplayVersion", VERSION), ("Publisher", "TecnikGeek"),
                            ("DisplayIcon", icon), ("InstallLocation", dest),
                            ("UninstallString", f'"{exe}" {args} --uninstall'),
                            ("URLInfoAbout", "https://pietrodefilippis.it"),
                            ("InstallDate", installed_on), ("TkLaunchSchema", LAUNCH_SCHEMA)):
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        for name, value in (("EstimatedSize", size_kb), ("NoModify", 1), ("NoRepair", 1)):
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, value)


def refresh_after_update():
    """Dopo un aggiornamento automatico (che sostituisce solo i file): collegamenti su tk-tv.exe al posto di
    pythonw.exe (installazioni ≤ 1.0.8) e versione aggiornata in «App installate». Solo per la copia installata."""
    import winreg
    root = source_root()
    dest = existing_dest()
    if dest is None or os.path.normcase(os.path.abspath(dest)) != os.path.normcase(root):
        return False
    def value(name):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
                return winreg.QueryValueEx(k, name)[0]
        except OSError:
            return ""

    # la versione da sola non basta: lo script di aggiornamento delle versioni precedenti la scrive già lui
    changed = (value("TkLaunchSchema") != LAUNCH_SCHEMA or value("DisplayVersion") != VERSION
               or os.path.basename(app_exe(root)) not in value("UninstallString"))
    if changed:
        register(root, has_desktop_shortcut())
    if value("TkLaunchSchema") == LAUNCH_SCHEMA:
        cleanup_launchers(root)  # solo con i collegamenti già spostati su tk-tv.exe
    return changed


def cleanup_launchers(root):
    """Toglie python.exe e pythonw.exe dalla copia installata, così nella cartella resta solo tk-tv.exe.
    Solo quando l'app sta già girando come tk-tv.exe (collegamenti aggiornati); se il file è in uso si riprova
    al prossimo avvio."""
    import sys
    exe = os.path.join(root, "python", EXE_NAME)
    if not os.path.isfile(exe) or os.path.normcase(os.path.abspath(sys.executable)) != os.path.normcase(exe):
        return
    for name in ("pythonw.exe", "python.exe"):
        try:
            os.remove(os.path.join(root, "python", name))
        except OSError:
            pass


def launch(dest):
    subprocess.Popen([app_exe(dest), os.path.join(dest, "run.py")], cwd=dest,
                     creationflags=0x00000200, close_fds=True)


# ---------------------------------------------------------------- interfaccia
def run(argv):
    dest = existing_dest() or default_dest()
    desktop_default = existing_dest() is None or has_desktop_shortcut()
    if "--silent" in argv:
        install(dest, desktop_default)
        return 0

    from PySide6.QtCore import QObject, Qt, Signal
    from PySide6.QtWidgets import (
        QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QVBoxLayout,
        QWidget,
    )
    from tktv import style as S
    from tktv.icon import app_icon, badge_pixmap

    app = QApplication(argv)
    app.setStyle("Fusion")
    app.setStyleSheet(S.QSS)
    app.setWindowIcon(app_icon())

    class Bridge(QObject):
        progress = Signal(int, str)
        finished = Signal(str)
        failed = Signal(str)

    dlg = QDialog()
    dlg.setWindowTitle(f"Installazione {APP_TITLE} {VERSION}")
    dlg.setMinimumWidth(540)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)

    header = QWidget()
    header.setObjectName("tkHeader")
    header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    h = QHBoxLayout(header)
    h.setContentsMargins(22, 18, 22, 18)
    h.setSpacing(14)
    ic = QLabel()
    ic.setPixmap(badge_pixmap(52, 14))
    h.addWidget(ic)
    h.addWidget(QLabel(f"<div style='font-size:20px;font-weight:800;color:white'>{APP_TITLE}</div>"
                       f"<div style='color:{S.GRAY300}'>Installazione versione {VERSION} · la TV in diretta della tua "
                       f"playlist M3U</div>"), 1)
    lay.addWidget(header)

    body = QVBoxLayout()
    body.setContentsMargins(26, 20, 26, 12)
    body.setSpacing(10)
    where = QLabel(f"tk-tv verrà installato in:<br><b>{dest}</b>")
    where.setWordWrap(True)
    body.addWidget(where)
    desktop_cb = QCheckBox("Crea un collegamento sul desktop")
    desktop_cb.setChecked(desktop_default)
    launch_cb = QCheckBox("Apri tk-tv al termine")
    launch_cb.setChecked(True)
    body.addWidget(desktop_cb)
    body.addWidget(launch_cb)
    info = QLabel("Non servono permessi di amministratore · nessun programma sconosciuto da approvare")
    info.setObjectName("muted")
    info.setWordWrap(True)
    body.addWidget(info)
    bar = QProgressBar()
    bar.setTextVisible(False)
    bar.setFixedHeight(8)
    bar.hide()
    body.addWidget(bar)
    status = QLabel("")
    status.setObjectName("soft")
    body.addWidget(status)
    lay.addLayout(body)

    footer = QWidget()
    footer.setObjectName("tkZipFooter")
    footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    footer.setStyleSheet(f"#tkZipFooter {{ background:{S.NAVY2}; }}")
    f = QHBoxLayout(footer)
    f.setContentsMargins(26, 12, 26, 12)
    f.addWidget(QLabel(f"<span style='color:{S.GRAY500}'>Creato da TecnikGeek</span>"))
    f.addStretch(1)
    cancel = QPushButton("Annulla")
    ok = QPushButton("Installa")
    ok.setObjectName("accent")
    ok.setDefault(True)
    f.addWidget(cancel)
    f.addWidget(ok)
    lay.addWidget(footer)

    bridge = Bridge()
    state = {"done": False}

    def on_progress(p, s):
        bar.setValue(p)
        status.setText(s)

    def on_finished(_path):
        state["done"] = True
        status.setText("✔ tk-tv è installato. Lo trovi nel menu Start" + (" e sul desktop." if desktop_cb.isChecked() else "."))
        status.setStyleSheet(f"color:{S.GREEN}; font-weight:600;")
        ok.setText("Fine")
        ok.setEnabled(True)

    def on_failed(msg):
        QMessageBox.critical(dlg, APP_TITLE, f"Installazione non riuscita:\n{msg}")
        for w in (ok, cancel, desktop_cb, launch_cb):
            w.setEnabled(True)
        bar.hide()
        status.setText("")

    bridge.progress.connect(on_progress)
    bridge.finished.connect(on_finished)
    bridge.failed.connect(on_failed)

    def start():
        if state["done"]:
            if launch_cb.isChecked():
                launch(dest)
            dlg.accept()
            return
        for w in (ok, cancel, desktop_cb, launch_cb):
            w.setEnabled(False)
        bar.show()
        desktop = desktop_cb.isChecked()

        def work():
            try:
                install(dest, desktop, lambda p, s: bridge.progress.emit(p, s))
                bridge.finished.emit(dest)
            except Exception as exc:
                bridge.failed.emit(str(exc))

        threading.Thread(target=work, daemon=True).start()

    ok.clicked.connect(start)
    cancel.clicked.connect(dlg.reject)
    dlg.exec()
    return 0
