#!/bin/bash
# Crea dist/tk-tv-player-linux-<versione>-<arch>.AppImage (Python, PySide6 e libVLC inclusi). Da eseguire su Ubuntu
# (runner ubuntu-22.04 di GitHub o PC di casa): non installa niente nel sistema.
# libVLC: dai pacchetti Ubuntu (apt-get download + dpkg-deb -x, vedi linux/includi_vlc.py).
# Uso: bash linux/build_linux.sh            (sul PC di casa: flock /tmp/tk-build.lock bash linux/build_linux.sh)
# Usa al massimo METÀ dei processori (JOBS per cambiarlo): con tutti, sul PC di casa la memoria si riempie.
# TK_SELFTEST_FINESTRA=1: il selftest video usa anche la finestra vera (X11/XWayland) per qualche secondo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
JOBS="${JOBS:-$(( $(nproc) / 2 > 0 ? $(nproc) / 2 : 1 ))}"
if [ -z "${TK_BUILD_LIMITATA:-}" ] && command -v taskset >/dev/null; then
    export TK_BUILD_LIMITATA=1
    exec nice -n 10 taskset -c "0-$(( JOBS - 1 ))" bash "$0" "$@"
fi
ARCH="$(uname -m)"
PY="${PYTHON:-python3}"
VERSION="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' tktv/__init__.py | tr -d '\r')"
APPIMAGETOOL_VER="1.9.0"
TOOLS="${TK_STRUMENTI_BUILD:-$HOME/.cache/tk-build}"
echo "== tk-tv $VERSION per Linux ($ARCH), $JOBS processori"
command -v ffmpeg >/dev/null || { echo "Serve ffmpeg per creare il video di prova del selftest"; exit 1; }

$PY -m venv .venv-linux
# shellcheck disable=SC1091
source .venv-linux/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet "pyside6-essentials==6.11.*" python-vlc certifi jeepney pyinstaller patchelf

rm -rf build dist build-licenze
mkdir -p build dist build-licenze/licenze

echo "== libVLC dai pacchetti Ubuntu (niente installato nel sistema)"
export TK_DEB_CACHE="$TOOLS/tk-tv-deb-$(lsb_release -cs 2>/dev/null || echo ubuntu)-$ARCH"
python -I linux/includi_vlc.py vlc build/vlc build/vlc-lavoro build-licenze/licenze build/qt-xcb
VLC_VER="$(cat build/vlc-lavoro/vlc-versione.txt)"

echo "== licenze e icona"
SITE="$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
PYLIC=""
for c in "$(python -c 'import os, sys; print(os.path.join(sys.base_prefix, "lib", "python%d.%d" % sys.version_info[:2], "LICENSE.txt"))')" \
         "/usr/share/doc/python3.$(python -c 'import sys; print(sys.version_info[1])')/copyright"; do
    [ -f "$c" ] && { PYLIC="$c"; break; }
done
python -I installer/licenze.py build-licenze/licenze --site "$SITE" --python-licenza "$PYLIC" --linux --vlc-versione "$VLC_VER"
QT_QPA_PLATFORM=offscreen python -c '
import sys; sys.path.insert(0, ".")
from PySide6.QtGui import QGuiApplication
app = QGuiApplication(sys.argv)
from tktv.icon import render_icon
render_icon(512).save("build/tk-tv-512.png")'

echo "== programma"
pyinstaller --noconfirm --clean --log-level WARN --workpath build/pyinstaller linux/tk-tv-linux.spec
INTERNAL="dist/tk-tv/_internal"
[ -f "$INTERNAL/licenze/COPYING-AGPL-3.0.txt" ] && [ -f "$INTERNAL/licenze/LINUX-PACCHETTI.txt" ] || { echo "Mancano le licenze nel pacchetto"; exit 1; }
# libVLC con cp -a (date intatte: la cache plugins.dat resta valida)
cp -a build/vlc "$INTERNAL/vlc"
echo "   plugin VLC inclusi: $(find "$INTERNAL/vlc/plugins" -name '*_plugin.so' | wc -l)"

echo "== controllo delle librerie (ldd)"
python -I linux/includi_vlc.py controlla dist/tk-tv

echo "== AppImage"
APPDIR="build/AppDir"
rm -rf "$APPDIR" && mkdir -p "$APPDIR/usr/lib"
cp -a dist/tk-tv "$APPDIR/usr/lib/tk-tv"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/tk-tv/tk-tv" "$@"
EOF
chmod 755 "$APPDIR/AppRun"
cat > "$APPDIR/tk-tv.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=tk-tv
GenericName=Lettore TV
Comment=Lettore della TV in diretta dalla tua lista M3U (TecnikGeek)
Exec=tk-tv %U
Icon=tk-tv
Terminal=false
Categories=AudioVideo;Video;Player;TV;
StartupWMClass=tk-tv
EOF
cp build/tk-tv-512.png "$APPDIR/tk-tv.png"
ln -sf tk-tv.png "$APPDIR/.DirIcon"

TOOL="$TOOLS/appimagetool-$APPIMAGETOOL_VER-$ARCH.AppImage"
if [ ! -x "$TOOL" ]; then
    mkdir -p "$TOOLS"
    curl -fsSL -o "$TOOL.part" \
        "https://github.com/AppImage/appimagetool/releases/download/$APPIMAGETOOL_VER/appimagetool-$ARCH.AppImage"
    chmod 755 "$TOOL.part" && mv "$TOOL.part" "$TOOL"
fi
OUT="dist/tk-tv-player-linux-$VERSION-$ARCH.AppImage"
rm -f "$OUT"
APPIMAGE_EXTRACT_AND_RUN=1 ARCH="$ARCH" "$TOOL" --no-appstream \
    --mksquashfs-opt -processors --mksquashfs-opt "$JOBS" "$APPDIR" "$OUT" > build/appimagetool.log 2>&1 || {
    tail -n 30 build/appimagetool.log; echo "CREAZIONE APPIMAGE FALLITA"; exit 1; }
chmod 755 "$OUT"
echo "== Creato $OUT ($(du -h "$OUT" | cut -f1); cartella $(du -sh dist/tk-tv | cut -f1), di cui libVLC $(du -sh build/vlc | cut -f1))"

echo "== selftest (dal file AppImage): interfaccia + libVLC"
SHOT="$ROOT/dist/selftest-linux-$ARCH.png"
rm -f "$SHOT" "$SHOT.err"
TKTV_PROFILE=selftest QT_QPA_PLATFORM=offscreen timeout 90 "$OUT" --selftest "$SHOT" || true
[ -f "$SHOT.err" ] && { echo "SELFTEST: libVLC non parte - $(cat "$SHOT.err")"; exit 1; }
[ -f "$SHOT" ] || { echo "SELFTEST FALLITO: il programma non si avvia"; exit 1; }
echo "   interfaccia OK"

echo "== selftest video: riproduce qualche secondo di un video di prova generato ora"
PROVA="build/prova.ts"
# contenuto neutro: barre di prova, orologio che scorre e audio muto; H.264 come i canali (MPEG-2 se manca x264)
ffmpeg -loglevel error -y -f lavfi -i "testsrc2=size=1280x720:rate=25" -f lavfi -i "anullsrc=r=48000:cl=stereo" \
    -t 25 -c:v libx264 -preset veryfast -pix_fmt yuv420p -g 25 -c:a aac -b:a 64k -f mpegts "$PROVA" 2>/dev/null || \
ffmpeg -loglevel error -y -f lavfi -i "testsrc2=size=1280x720:rate=25" -f lavfi -i "anullsrc=r=48000:cl=stereo" \
    -t 25 -c:v mpeg2video -q:v 4 -c:a mp2 -f mpegts "$PROVA"
VTXT="$ROOT/dist/selftest-video-linux-$ARCH.txt"
rm -f "$VTXT"
QT_QPA_PLATFORM=offscreen timeout 120 "$OUT" --selftest-video "$PROVA" "$VTXT" > /dev/null 2>&1 || true
cat "$VTXT" 2>/dev/null || true
grep -q "^OK" "$VTXT" 2>/dev/null || { echo "SELFTEST VIDEO FALLITO"; exit 1; }
if [ "${TK_SELFTEST_FINESTRA:-0}" = "1" ] && [ -n "${DISPLAY:-}" ]; then
    echo "== selftest video nella finestra vera (X11/XWayland, si chiude da sola)"
    WTXT="$ROOT/dist/selftest-video-finestra-linux-$ARCH.txt"
    rm -f "$WTXT"
    env -u QT_QPA_PLATFORM timeout 120 "$OUT" --selftest-video "$PROVA" "$WTXT" > /dev/null 2>&1 || true
    cat "$WTXT" 2>/dev/null || true
    grep -q "^OK" "$WTXT" 2>/dev/null || { echo "SELFTEST VIDEO IN FINESTRA FALLITO"; exit 1; }
fi

if [ "${SKIP_UPDATE_TEST:-0}" != "1" ]; then
    echo "== test aggiornamento automatico (manifest finto 99.0.0 firmato -> sostituzione del file AppImage)"
    WORK="$(mktemp -d)"
    TESTAPP="$WORK/Programmi/tk-tv.AppImage"     # copia «installata» che deve essere sostituita
    mkdir -p "$(dirname "$TESTAPP")"
    cp "$OUT" "$TESTAPP"
    BEFORE="$(stat -c %i "$TESTAPP")"
    COPY="$WORK/tk-tv-nuova.AppImage"
    cp "$OUT" "$COPY"   # lo script di aggiornamento cancella il file usato
    SHA="$(sha256sum "$COPY" | cut -d' ' -f1)"
    SIZE="$(stat -c %s "$COPY")"
    MANIFEST="$WORK/tk-tv-player-linux.json"
    printf '{"version":"99.0.0","notes":["test"],"linux-%s":{"url":"file://%s","sha256":"%s","size":%s}}' \
        "$ARCH" "$COPY" "$SHA" "$SIZE" > "$MANIFEST"
    # aggiornamenti firmati: chiave usa e getta solo per questo test (la vera resta sul PC di Pietro);
    # lo slug è il nome del manifest, come in updater.SLUG
    read -r SEME PUB <<< "$(python mac/firma_aggiornamenti.py prova)"
    TK_FIRMA_SEME_PROVA="$SEME" python mac/firma_aggiornamenti.py firma --slug tk-tv-player-linux "$MANIFEST"
    export XDG_DATA_HOME="$WORK/dati"   # log del test e dati di prova fuori da quelli veri
    LOGT="$XDG_DATA_HOME/tk-tv-player/update-test.log"
    # prima la prova contraria: manifest firmato con un'altra chiave = rifiutato
    read -r _ ALTRA <<< "$(python mac/firma_aggiornamenti.py prova)"
    TK_AGGIORNAMENTI_PROVA="$ALTRA" "$TESTAPP" --update-test "file://$MANIFEST" --no-relaunch || true
    grep -q "rifiutato" "$LOGT" || { cat "$LOGT"; echo "TEST FIRMA FALLITO: accettato con la chiave sbagliata"; exit 1; }
    [ "$(stat -c %i "$TESTAPP")" = "$BEFORE" ] || { echo "TEST FIRMA FALLITO: file sostituito"; exit 1; }
    TK_AGGIORNAMENTI_PROVA="$PUB" "$TESTAPP" --update-test "file://$MANIFEST" --no-relaunch
    AFTER="$BEFORE"
    for _ in $(seq 1 120); do
        AFTER="$(stat -c %i "$TESTAPP" 2>/dev/null || echo "$BEFORE")"
        [ "$AFTER" != "$BEFORE" ] && [ ! -f "$COPY" ] && break
        sleep 1
    done
    sleep 1
    cat "$LOGT" "$XDG_DATA_HOME/tk-tv-player/aggiornamento.log" 2>/dev/null || true
    unset XDG_DATA_HOME
    if [ "$AFTER" = "$BEFORE" ] || [ ! -x "$TESTAPP" ] || ! cmp -s "$TESTAPP" "$OUT"; then
        echo "TEST AGGIORNAMENTO FALLITO"
        exit 1
    fi
    rm -rf "$WORK"
    echo "   aggiornamento OK (file AppImage sostituito, firma sbagliata rifiutata)"
fi
echo "== Fatto: $OUT"
