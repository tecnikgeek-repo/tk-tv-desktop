#!/bin/bash
# Crea dist/tk-tv-player-mac-<versione>-<arch>.dmg («TK TV.app» con Python, PySide6 e libVLC inclusi).
# Da eseguire su un Mac. libVLC: dmg ufficiale VideoLAN in vendor/ (vedi sotto, SHA-256 verificato).
# Uso: bash mac/build_mac.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ARCH="$(uname -m)"
VERSION="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' tktv/__init__.py)"
VLC_VER="3.0.24"
VLC_SHA="2c8e89f7f42e53c2fb0e87b6dfa39b49f1364b25080aaa2e476ac74c0d7beb3c"
echo "== tk-tv $VERSION per macOS ($ARCH)"

# --- ambiente Python (uv: Python 3.13 senza toccare quello di sistema)
UV="${UV:-$(command -v uv || echo "$HOME/.local/bin/uv")}"
if [ ! -x .venv-mac/bin/python ]; then
    "$UV" venv -q --python 3.13 .venv-mac
fi
"$UV" pip install -q --python .venv-mac/bin/python "pyside6-essentials==6.11.*" python-vlc certifi pyinstaller
PY=.venv-mac/bin/python

# --- libVLC dal dmg ufficiale (universale, firmato VideoLAN)
DMG_VLC="vendor/vlc-$VLC_VER-universal.dmg"
VLC_SRC="vendor/vlc-$VLC_VER"
if [ ! -f "$VLC_SRC/lib/libvlc.dylib" ]; then
    mkdir -p vendor
    [ -f "$DMG_VLC" ] || curl -sSL -o "$DMG_VLC" "https://get.videolan.org/vlc/$VLC_VER/macosx/vlc-$VLC_VER-universal.dmg"
    echo "$VLC_SHA  $DMG_VLC" | shasum -a 256 -c -
    MNT="$(mktemp -d)"
    hdiutil attach -quiet -nobrowse -readonly -mountpoint "$MNT" "$DMG_VLC"
    mkdir -p "$VLC_SRC"
    ditto "$MNT/VLC.app/Contents/MacOS/lib" "$VLC_SRC/lib"
    ditto "$MNT/VLC.app/Contents/MacOS/plugins" "$VLC_SRC/plugins"
    hdiutil detach -quiet "$MNT"
fi

echo "== icona"
$PY mac/make_icns.py

echo "== licenze"
rm -rf build dist build-licenze
# AGPL di tk-tv + testi dei componenti inclusi: il .spec li mette nelle risorse dell'app (cartella «licenze»)
SITE="$($PY -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
PYLIC="$($PY -c 'import os, sys; print(os.path.join(sys.base_prefix, "lib", "python%d.%d" % sys.version_info[:2], "LICENSE.txt"))')"
$PY -I installer/licenze.py build-licenze/licenze --site "$SITE" --python-licenza "$PYLIC" --mac

echo "== app"
$PY -m PyInstaller --noconfirm --clean --log-level WARN mac/tk-tv-mac.spec
APP="dist/TK TV.app"
# PyInstaller 6 mette i dati in Contents/Resources (con un collegamento in Contents/Frameworks, dove li cerca tk-tv)
[ -f "$APP/Contents/Resources/licenze/COPYING-AGPL-3.0.txt" ] && [ -e "$APP/Contents/Frameworks/licenze" ] || { echo "Mancano le licenze nell'app"; exit 1; }
# nome visibile (Finder, Dock, barra dei menu) «tk-tv»; il nome del bundle resta «TK TV.app» per gli aggiornamenti
for lang in Base en it; do
    mkdir -p "$APP/Contents/Resources/$lang.lproj"
    printf 'CFBundleName = "tk-tv";\nCFBundleDisplayName = "tk-tv";\n' > "$APP/Contents/Resources/$lang.lproj/InfoPlist.strings"
done

# libVLC con ditto (date intatte: plugins.dat resta valido)
VLC_DST="$APP/Contents/Frameworks/vlc"
ditto "$VLC_SRC/lib" "$VLC_DST/lib"
ditto "$VLC_SRC/plugins" "$VLC_DST/plugins"
# solo i plugin che servono a un player IPTV: VLC, cercando il modulo giusto, carica ogni candidato e
# macOS verifica la firma di ciascuno al primo caricamento (quasi un secondo l'uno). Elenco ricavato
# facendo girare tutti i canali della playlist, più sottotitoli, deinterlacciamento e conversioni audio.
KEEP="adaptive https http filesystem prefetch cache_read cache_block live555 udp rtp inflate skiptags
  ts es mp4 mkv ogg playlist ps wav h26x flacsys mpgv xml
  avcodec videotoolbox faad mpg123 opus vorbis flac speex lpcm araw g711 aes3 spdif a52 theora dav1d cvpx
  rawvideo subsdec subsusf cc zvbi telx dvbsub scte27 spudec cvdsub svcdsub substx3g webvtt ttml stl jpeg png
  freetype packetizer_* i420_* i422_* yuy2_* grey_yuv rv32 chain swscale glconv_cvpx yuvp
  caopengllayer vout_macosx deinterlace scale auhal float_mixer integer_mixer samplerate scaletempo
  audio_format trivial_channel_mixer simple_channel_mixer remap ugly_resampler speex_resampler soxr
  dolby_surround_decoder headphone_channel_mixer securetransport gnutls memory_keystore console_logger file_logger"
for f in "$VLC_DST"/plugins/*.dylib; do
    name="$(basename "$f")"; name="${name#lib}"; name="${name%_plugin.dylib}"
    keep=0
    for k in $KEEP; do
        # shellcheck disable=SC2053
        [[ "$name" == $k ]] && { keep=1; break; }
    done
    [ "$keep" = 1 ] || rm -f "$f"
done
rm -f "$VLC_DST"/plugins/*.jar
echo "   plugin VLC inclusi: $(ls "$VLC_DST"/plugins/*.dylib | wc -l | tr -d ' ')"

# firma ad-hoc del bundle (le librerie VideoLAN restano con la loro firma)
codesign --force --sign - "$APP"
codesign --verify "$APP"

echo "== selftest (interfaccia + libVLC)"
SHOT="$ROOT/dist/selftest-$ARCH.png"
rm -f "$SHOT" "$SHOT.err"
TKTV_PROFILE=selftest "$APP/Contents/MacOS/TK TV" --selftest "$SHOT" &
PID=$!
for _ in $(seq 1 90); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
kill "$PID" 2>/dev/null || true
[ -f "$SHOT.err" ] && { echo "SELFTEST: libVLC non parte - $(cat "$SHOT.err")"; exit 1; }
[ -f "$SHOT" ] || { echo "SELFTEST FALLITO: l'app non si avvia"; exit 1; }
echo "   selftest OK"
rm -rf "$HOME/Library/Application Support/tk-tv-player-selftest" "$HOME/Library/Preferences/"*tk-tv-player-selftest*

echo "== dmg"
STAGE="$(mktemp -d)"
ditto "$APP" "$STAGE/TK TV.app"
ln -s /Applications "$STAGE/Applicazioni"
cp mac/LEGGIMI.txt "$STAGE/Leggimi - primo avvio.txt"
DMG="dist/tk-tv-player-mac-$VERSION-$ARCH.dmg"
hdiutil create -quiet -volname "tk-tv $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"
echo "== Creato $DMG ($(du -h "$DMG" | cut -f1))"

if [ "${SKIP_UPDATE_TEST:-0}" != "1" ]; then
    echo "== test aggiornamento automatico (manifest finto 99.0.0 -> sostituzione del bundle)"
    TESTDIR="$(mktemp -d)"
    TESTAPP="$TESTDIR/TK TV.app"
    ditto "$APP" "$TESTAPP"
    BEFORE="$(stat -f %i "$TESTAPP/Contents/Info.plist")"
    COPY="$TESTDIR/tk-tv-test.dmg"
    cp "$DMG" "$COPY"   # lo script di aggiornamento cancella il dmg usato
    SHA="$(shasum -a 256 "$COPY" | cut -d' ' -f1)"
    SIZE="$(stat -f %z "$COPY")"
    printf '{"version":"99.0.0","notes":["test"],"mac-%s":{"url":"file://%s","sha256":"%s","size":%s}}' "$ARCH" "$COPY" "$SHA" "$SIZE" > "$TESTDIR/m.json"
    # aggiornamenti firmati: chiave usa e getta solo per questo test (la vera resta sul PC di Pietro)
    read -r SEME PUB <<< "$($PY mac/firma_aggiornamenti.py prova)"
    TK_FIRMA_SEME_PROVA="$SEME" $PY mac/firma_aggiornamenti.py firma --slug tk-tv-player-mac "$TESTDIR/m.json"
    TK_AGGIORNAMENTI_PROVA="$PUB" TKTV_PROFILE=selftest "$TESTAPP/Contents/MacOS/TK TV" --update-test "file://$TESTDIR/m.json" --no-relaunch
    AFTER="$BEFORE"
    for _ in $(seq 1 120); do
        AFTER="$(stat -f %i "$TESTAPP/Contents/Info.plist" 2>/dev/null || echo "$BEFORE")"
        [ "$AFTER" != "$BEFORE" ] && [ ! -f "$COPY" ] && break
        sleep 1
    done
    LOGDIR="$HOME/Library/Application Support/tk-tv-player-selftest"
    cat "$LOGDIR/update-test.log" "$LOGDIR/aggiornamento.log" 2>/dev/null || true
    rm -rf "$LOGDIR"
    if [ "$AFTER" = "$BEFORE" ] || [ ! -x "$TESTAPP/Contents/MacOS/TK TV" ]; then
        echo "TEST AGGIORNAMENTO FALLITO"
        exit 1
    fi
    rm -rf "$TESTDIR"
    echo "   aggiornamento OK (bundle sostituito)"
fi
