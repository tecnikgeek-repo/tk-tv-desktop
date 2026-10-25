"""Disinstallazione della versione installata (senza exe dedicati: compatibile con Smart App Control)."""
import ctypes
import os
import subprocess
from ctypes import wintypes

UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\tk-tv-player"
MB_YESNO, MB_ICONQUESTION, MB_ICONINFO, IDYES = 0x04, 0x20, 0x40, 6
SHORTCUT = "tk-tv.lnk"
LEGACY_SHORTCUTS = ("TK TV.lnk", "tkTV.lnk")  # nomi dei collegamenti: fino alla 1.0.12 · 1.0.13–1.0.14


def _msg(text, flags):
    return ctypes.windll.user32.MessageBoxW(None, text, "tk-tv", flags)


def _process_paths():
    """Ritorna [(pid, percorso exe)] dei processi visibili (API Win32, niente dipendenze)."""
    psapi, kernel = ctypes.windll.psapi, ctypes.windll.kernel32
    arr = (wintypes.DWORD * 4096)()
    needed = wintypes.DWORD()
    psapi.EnumProcesses(ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(needed))
    out = []
    for pid in arr[:needed.value // ctypes.sizeof(wintypes.DWORD)]:
        h = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            continue
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if kernel.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                out.append((pid, buf.value))
        finally:
            kernel.CloseHandle(h)
    return out


def kill_other_instances(root):
    prefix = os.path.normcase(os.path.join(root, ""))
    for pid, path in _process_paths():
        if pid != os.getpid() and os.path.normcase(path).startswith(prefix):
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=0x08000000)


def run():
    import winreg

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not any(os.path.exists(os.path.join(root, "python", n)) for n in ("tk-tv.exe", "pythonw.exe")):
        _msg("La disinstallazione è disponibile solo per la versione installata di tk-tv.", MB_ICONINFO)
        return 0
    if _msg("Vuoi disinstallare tk-tv?\n\nIl link della playlist e i preferiti restano salvati nel tuo profilo.",
            MB_YESNO | MB_ICONQUESTION) != IDYES:
        return 0

    kill_other_instances(root)
    shell = ctypes.windll.shell32
    for folder_id in (0x0002, 0x0010):  # CSIDL_PROGRAMS, CSIDL_DESKTOPDIRECTORY
        buf = ctypes.create_unicode_buffer(260)
        if shell.SHGetFolderPathW(None, folder_id, None, 0, buf) == 0:
            for name in (SHORTCUT,) + LEGACY_SHORTCUTS:
                lnk = os.path.join(buf.value, name)
                try:
                    if os.path.exists(lnk):
                        os.remove(lnk)
                except OSError:
                    pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass

    _msg("tk-tv è stato disinstallato.", MB_ICONINFO)
    # cancella solo i file di tk-tv (mai la cartella intera con /s) dopo la chiusura di questo processo
    q = lambda p: f'"{p}"'
    cmd = (f"ping 127.0.0.1 -n 4 >nul & rmdir /s /q {q(os.path.join(root, 'python'))}"
           f" & rmdir /s /q {q(os.path.join(root, 'tktv'))} & rmdir /s /q {q(os.path.join(root, 'assets'))}"
           f" & rmdir /s /q {q(os.path.join(root, 'vlc'))} & rmdir /s /q {q(os.path.join(root, 'licenze'))}"
           f" & del /q {q(os.path.join(root, 'run.py'))}"
           f" & rmdir {q(root)}")
    subprocess.Popen(["cmd.exe", "/c", cmd], cwd=os.environ.get("TEMP", "C:\\"), creationflags=0x08000000 | 0x00000008,
                     close_fds=True)
    return 0
