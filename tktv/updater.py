"""Aggiornamenti automatici: controllo del manifest, download verificato (SHA-256) e installazione.

Stesso schema di tk-pdf. Windows: il pacchetto è uno ZIP che uno script con soli strumenti di sistema
(cmd, tar, reg) sostituisce alla cartella installata, così Smart App Control non deve valutare
nessun eseguibile nuovo. Mac: un .dmg da cui uno script bash copia «TK TV.app» al posto di quella
installata. In caso di errore resta la versione precedente.
"""
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

from tktv import VERSION
from tktv.tk_aggiornamento import asset_valido
from tktv.playlist import _ssl_context
from tktv.util import app_data_dir, app_root

def _codice_conteggio():
    """«; <codice>» per il manifest: conta l'installazione una volta sola anche se cambia rete (Privacy 4-ter)."""
    try:
        from tktv import tk_licenza
        return f"; {tk_licenza.CODICE_CONTEGGIO}" if tk_licenza.CODICE_CONTEGGIO else ""
    except Exception:
        return ""


IS_MAC = sys.platform == "darwin"
MANIFEST_URL = ("https://pietrodefilippis.it/updates/tk-tv-player-mac.json" if IS_MAC
                else "https://pietrodefilippis.it/updates/tk-tv-player-windows.json")
CHECK_INTERVAL = 12 * 3600
# nome del manifest (tk-pdf, tk-tv-player-mac…): entra nel testo firmato
SLUG = MANIFEST_URL.rsplit("/", 1)[-1][:-len(".json")]

# Mac: sostituisce il bundle dopo la chiusura di tk-tv, con ripristino in caso di errore.
MAC_SCRIPT = r'''#!/bin/bash
PID="$1"; DMG="$2"; TARGET="$3"; RELAUNCH="$4"; LOG="$5"; NEWVER="$6"
exec >>"$LOG" 2>&1
echo "[$(date)] aggiornamento a $NEWVER: $DMG -> $TARGET"
for _ in $(seq 1 120); do kill -0 "$PID" 2>/dev/null || break; sleep 0.5; done
MNT="$(mktemp -d /tmp/tktv-mnt.XXXXXX)"
if ! hdiutil attach -nobrowse -readonly -noautoopen -mountpoint "$MNT" "$DMG"; then
  echo "AGGIORNAMENTO NON RIUSCITO: montaggio dmg fallito"
  [ "$RELAUNCH" = "1" ] && open "$TARGET"
  exit 1
fi
PARENT="$(dirname "$TARGET")"
STAGE="$PARENT/.tktv-nuova.app"
OLD="$PARENT/.tktv-vecchia.app"
rm -rf "$STAGE" "$OLD"
if ditto "$MNT/TK TV.app" "$STAGE" && [ -x "$STAGE/Contents/MacOS/TK TV" ] && mv "$TARGET" "$OLD" && mv "$STAGE" "$TARGET"; then
  rm -rf "$OLD"
  echo "app sostituita"
else
  echo "AGGIORNAMENTO NON RIUSCITO: versione precedente mantenuta"
  [ -d "$TARGET" ] || mv "$OLD" "$TARGET"
  rm -rf "$STAGE"
fi
xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null
hdiutil detach "$MNT" -quiet
rmdir "$MNT" 2>/dev/null
rm -f "$DMG"
if [ "$RELAUNCH" = "1" ]; then open "$TARGET"; fi
echo "fine"
'''

WIN_SCRIPT = r'''@echo off
setlocal
set "PID=%~1"
set "ZIP=%~2"
set "DIR=%~3"
set "RELAUNCH=%~4"
set "LOG=%~5"
set "NEWVER=%~6"
>>"%LOG%" echo [%date% %time%] aggiornamento a %NEWVER%: %ZIP%
rem nessuna attesa sul PID: finché tk-tv è aperto la cartella non si può rinominare (vedi :moveold)
ping 127.0.0.1 -n 3 >nul
set "NEW=%DIR%.nuova"
set "OLD=%DIR%.vecchia"
if exist "%NEW%" rmdir /s /q "%NEW%"
if exist "%OLD%" rmdir /s /q "%OLD%"
mkdir "%NEW%"
tar -xf "%ZIP%" -C "%NEW%"
if errorlevel 1 goto fail
if not exist "%NEW%\python\tk-tv.exe" if not exist "%NEW%\python\pythonw.exe" goto fail
if not exist "%NEW%\run.py" goto fail
if not exist "%NEW%\vlc\libvlc.dll" goto fail
set /a TRIES=0
:moveold
move "%DIR%" "%OLD%" >nul 2>&1
if not errorlevel 1 goto movenew
set /a TRIES+=1
if %TRIES% GEQ 60 goto fail
ping 127.0.0.1 -n 2 >nul
goto moveold
:movenew
move "%NEW%" "%DIR%" >nul 2>&1
if errorlevel 1 (
  move "%OLD%" "%DIR%" >nul 2>&1
  goto fail
)
rmdir /s /q "%OLD%"
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\tk-tv-player" /v DisplayVersion /d "%NEWVER%" /f >nul 2>&1
>>"%LOG%" echo cartella sostituita
del /q "%ZIP%" >nul 2>&1
call :exe
if "%RELAUNCH%"=="1" start "" "%EXE%" "%DIR%\run.py"
>>"%LOG%" echo fine
exit /b 0
:fail
>>"%LOG%" echo AGGIORNAMENTO NON RIUSCITO: versione precedente mantenuta
if exist "%NEW%" rmdir /s /q "%NEW%"
call :exe
if "%RELAUNCH%"=="1" if exist "%DIR%\run.py" start "" "%EXE%" "%DIR%\run.py"
exit /b 1
:exe
set "EXE=%DIR%\python\pythonw.exe"
if exist "%DIR%\python\tk-tv.exe" set "EXE=%DIR%\python\tk-tv.exe"
exit /b 0
'''


def parse_version(value):
    parts = [int(x) for x in re.findall(r"\d+", str(value))[:3]]
    return tuple(parts + [0] * (3 - len(parts)))


def is_newer(remote, local=VERSION):
    return parse_version(remote) > parse_version(local)


def _open(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": f"tk-tv-player/{VERSION} ({platform_key()}{_codice_conteggio()})",
                                               "Cache-Control": "no-cache"})
    if url.startswith("https:"):
        return urllib.request.urlopen(req, timeout=timeout, context=_ssl_context())
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_manifest(url=MANIFEST_URL, timeout=12):
    if url.startswith("http"):
        # il server mette in cache i .json per giorni: parametro anti-cache
        url += ("&" if "?" in url else "?") + f"t={int(time.time())}"
    with _open(url, timeout) as resp:
        data = json.loads(resp.read().decode("utf-8-sig"))
    if not isinstance(data, dict) or "version" not in data:
        raise ValueError("risposta del server non valida")
    return data


def platform_key():
    if IS_MAC:
        # sotto Rosetta platform.machine() dice x86_64: arriva la stessa build che sta girando
        return "mac-arm64" if platform.machine() == "arm64" else "mac-x86_64"
    return "windows"


def asset_for(manifest):
    key = platform_key() if IS_MAC else "windows-zip"
    asset = manifest.get(key)
    return asset if isinstance(asset, dict) and asset.get("url") and asset_valido(SLUG, manifest, key, asset) else None


def install_kind():
    """'windows' o 'mac' se l'app è installata e quindi aggiornabile; None in sviluppo."""
    if IS_MAC:
        return "mac" if getattr(sys, "frozen", False) and mac_bundle_path() else None
    bundled = os.path.join(app_root(), "python")
    if any(os.path.exists(os.path.join(bundled, n)) for n in ("tk-tv.exe", "pythonw.exe")) and \
            os.path.normcase(os.path.abspath(sys.base_prefix)) == os.path.normcase(bundled):
        return "windows"
    return None


def mac_bundle_path():
    exe = os.path.abspath(sys.executable)
    i = exe.find(".app/Contents/MacOS/")
    return exe[:i + 4] if i >= 0 else None


def download_dir():
    path = os.path.join(tempfile.gettempdir(), "tk-tv-player-update")
    os.makedirs(path, exist_ok=True)
    return path


def download(url, dest, sha256=None, progress=None, cancelled=None):
    digest = hashlib.sha256()
    tmp = dest + ".part"
    with _open(url, 60) as resp, open(tmp, "wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancelled and cancelled():
                fh.close()
                os.remove(tmp)
                raise InterruptedError("download annullato")
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            fh.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if not sha256 or digest.hexdigest().lower() != str(sha256).lower():
        os.remove(tmp)
        raise ValueError("il file scaricato non è integro (verifica SHA-256 non riuscita). Riprova.")
    os.replace(tmp, dest)
    return dest


def apply_update(path, relaunch=True, new_version=""):
    """Avvia l'installazione dell'aggiornamento. Subito dopo il chiamante deve chiudere tk-tv."""
    if IS_MAC:
        bundle = mac_bundle_path()
        parent = os.path.dirname(bundle)
        if not (os.access(parent, os.W_OK) and os.access(bundle, os.W_OK)):
            raise PermissionError(f"non hai i permessi per sostituire «{bundle}»")
        script = os.path.join(download_dir(), "applica-aggiornamento.sh")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(MAC_SCRIPT)
        log = os.path.join(app_data_dir(), "aggiornamento.log")
        subprocess.Popen(["/bin/bash", script, str(os.getpid()), path, bundle, "1" if relaunch else "0", log,
                          new_version], start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    # console nascosta (non DETACHED: senza console i comandi di sistema possono bloccarsi)
    flags = 0x00000200 | 0x08000000  # CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    script = os.path.join(download_dir(), "applica-aggiornamento.cmd")
    with open(script, "w", encoding="ascii", errors="replace", newline="\r\n") as fh:
        fh.write(WIN_SCRIPT)
    log = os.path.join(app_data_dir(), "aggiornamento.log")
    subprocess.Popen(["cmd.exe", "/c", script, str(os.getpid()), path, app_root(), "1" if relaunch else "0", log,
                      new_version], cwd=download_dir(), creationflags=flags, close_fds=True)


def cli_update_test(argv):
    """Test automatico senza interfaccia: --update-test <manifest_url> [--no-relaunch]."""
    url = argv[argv.index("--update-test") + 1]
    log = os.path.join(app_data_dir(), "update-test.log")

    def write(msg):
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")

    try:
        manifest = fetch_manifest(url)
        write(f"manifest {manifest['version']} (installata {VERSION})")
        if not is_newer(manifest["version"]):
            write("nessun aggiornamento")
            return 0
        asset = asset_for(manifest)
        if not asset:
            write(f"nessun file per {platform_key()}")
            return 2
        dest = os.path.join(download_dir(), os.path.basename(asset["url"].split("?")[0]))
        download(asset["url"], dest, asset.get("sha256"))
        write(f"scaricato e verificato: {dest}")
        if install_kind() is None:
            write("versione di sviluppo: aggiornamento non applicato")
            return 3
        apply_update(dest, relaunch="--no-relaunch" not in argv, new_version=manifest["version"])
        write("installazione avviata")
        return 0
    except Exception as exc:
        write(f"ERRORE: {exc}")
        return 1
