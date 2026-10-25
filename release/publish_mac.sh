#!/bin/bash
# Pubblica tk-tv per Mac: chi ce l'ha installata la riceve con l'aggiornamento automatico.
# Uso:  bash release/publish_mac.sh "Novità 1|Novità 2"
# Pubblica i dmg di questa versione presenti in dist/ (tk-tv-player-mac-<ver>-x86_64.dmg e/o -arm64.dmg).
# Si può rilanciare con la stessa versione per aggiungere l'altra architettura: le note restano quelle date.
# Prerequisiti: VERSION alzata in tktv/__init__.py, commit fatto, dmg creati con mac/build_mac.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
NOTES="${1:?Indica le novità: bash release/publish_mac.sh \"Novità 1|Novità 2\"}"
VERSION="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' tktv/__init__.py)"
SSHC="${SSH_CONFIG:-$HOME/Dropbox/CLAUDE/fleet/ssh-config}"
SLUG="tk-tv-player-mac"
REMOTE_DIR="public_html/updates/$SLUG"
BASE_URL="https://pietrodefilippis.it/updates/$SLUG"
MANIFEST_URL="https://pietrodefilippis.it/updates/$SLUG.json"
TK_APP="$HOME/Dropbox/CLAUDE/tk-software/tk-tv/Mac"
echo "== Pubblicazione tk-tv $VERSION per Mac"

[ -z "$(git status --porcelain)" ] || { echo "Ci sono modifiche non committate: fai commit prima di pubblicare"; exit 1; }

# --- sicurezza: mai una versione più vecchia di quella online
CURRENT="$(curl -fsS "$MANIFEST_URL?t=$(date +%s)" 2>/dev/null | sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' | head -1 || true)"
if [ -n "$CURRENT" ]; then
    NEWEST="$(printf '%s\n%s\n' "$CURRENT" "$VERSION" | sort -V | tail -1)"
    [ "$NEWEST" = "$VERSION" ] || { echo "Sul server c'è già la $CURRENT: alza VERSION"; exit 1; }
else
    echo "   nessun manifest precedente (prima pubblicazione)"
fi

DMGS=()
for arch in x86_64 arm64; do
    f="dist/$SLUG-$VERSION-$arch.dmg"
    [ -f "$f" ] && DMGS+=("$f")
done
[ ${#DMGS[@]} -gt 0 ] || { echo "Nessun dmg $VERSION in dist/: esegui mac/build_mac.sh"; exit 1; }

# --- manifest (chiavi mac-x86_64 / mac-arm64 come tk-pdf)
MANIFEST="$(mktemp)"
python3 - "$VERSION" "$NOTES" "$BASE_URL" "$MANIFEST" "${DMGS[@]}" <<'PY'
import hashlib, json, os, sys, time
version, notes, base, out, *dmgs = sys.argv[1:]
m = {"name": "tk-tv", "version": version, "date": time.strftime("%d/%m/%Y"),
     "notes": [n.strip() for n in notes.split("|") if n.strip()]}
for path in dmgs:
    arch = path.rsplit("-", 1)[1][:-4]
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    m[f"mac-{arch}"] = {"url": f"{base}/{os.path.basename(path)}", "sha256": sha, "size": os.path.getsize(path)}
json.dump(m, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=4)
PY
# firma del manifest (chiave segreta solo sul PC di Pietro): senza firma valida tk-tv non installa l'aggiornamento.
# Lo slug è il nome del manifest (tk-tv-player-mac): è quello che usa updater.SLUG nel programma.
# Il manifest si ricrea a ogni lancio con tutti i dmg presenti: la firma va sempre dopo, su quello finale.
FIRMA="${FIRMA_AGGIORNAMENTI:-$HOME/Dropbox/CLAUDE/tk-software/librerie/firma_aggiornamenti.py}"
python3 -I "$FIRMA" firma --slug "$SLUG" "$MANIFEST" || { echo "Firma del manifest non riuscita: niente pubblicazione"; rm -f "$MANIFEST"; exit 1; }

# --- upload: prima i file, per ultimo il manifest (così nessuno scarica file mancanti)
echo "   caricamento sul server…"
ssh -F "$SSHC" pietrodefilippis "mkdir -p ~/$REMOTE_DIR/old"
for f in "${DMGS[@]}"; do scp -q -F "$SSHC" "$f" "pietrodefilippis:~/$REMOTE_DIR/"; done
chmod 644 "$MANIFEST"   # mktemp crea il file 0600: sul server il manifest darebbe 403
scp -q -F "$SSHC" "$MANIFEST" "pietrodefilippis:~/public_html/updates/$SLUG.json.new"
# le versioni precedenti vanno in old/ (resta solo la penultima), poi si attiva il manifest
ssh -F "$SSHC" pietrodefilippis "cd ~/$REMOTE_DIR && old=\$(ls $SLUG-*.dmg | grep -v -- '-$VERSION-' || true); \
  if [ -n \"\$old\" ]; then rm -f old/*; mv -f \$old old/; fi; \
  mv -f ~/public_html/updates/$SLUG.json.new ~/public_html/updates/$SLUG.json && chmod 644 ~/public_html/updates/$SLUG.json && ls -la ~/$REMOTE_DIR"
rm -f "$MANIFEST"

# --- verifica pubblica
ONLINE="$(curl -fsS "$MANIFEST_URL?t=$(date +%s)")"
echo "$ONLINE" | grep -q "\"version\": \"$VERSION\"" || { echo "Il manifest pubblico non mostra $VERSION"; exit 1; }
for f in "${DMGS[@]}"; do
    size="$(curl -fsSI "$BASE_URL/$(basename "$f")" | awk 'tolower($1)=="content-length:"{print $2}' | tr -d '\r')"
    [ "$size" = "$(wc -c < "$f" | tr -d " ")" ] || { echo "Dimensione errata online: $(basename "$f")"; exit 1; }
done
echo "   manifest e file online verificati"

# --- codice sorgente di questa versione su GitHub (Informazioni > Licenze punta a .../tree/v<versione>)
GIT_REMOTE="$(git remote | grep -qx github && echo github || echo origin)"
git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null || git tag "v$VERSION"
git push "$GIT_REMOTE" "v$VERSION" || { echo "Invio del tag v$VERSION a GitHub non riuscito"; exit 1; }

# --- cartella tk-app di Dropbox: un solo ZIP per la consegna (i dmg delle due architetture + leggimi), solo l'ultima versione
# (per un'architettura mancante in dist/ si mette la build della release GitHub: gh release download v$VERSION -p '*.dmg' -D dist)
ZIP="$(mktemp -d)/$SLUG-$VERSION.zip"
cp mac/LEGGIMI-ZIP.txt "$(dirname "$ZIP")/Leggimi - quale scegliere.txt"
if command -v zip >/dev/null; then
    zip -q -j -0 "$ZIP" "${DMGS[@]}" "$(dirname "$ZIP")/Leggimi - quale scegliere.txt"
else  # su Windows (Git Bash) zip non c'è: stesso archivio con Python, senza compressione
    python -c 'import sys, zipfile, os; z = zipfile.ZipFile(sys.argv[1], "w", zipfile.ZIP_STORED); [z.write(f, os.path.basename(f)) for f in sys.argv[2:]]; z.close()' "$ZIP" "${DMGS[@]}" "$(dirname "$ZIP")/Leggimi - quale scegliere.txt"
fi
find "$TK_APP" -maxdepth 1 \( -name "$SLUG-*.dmg" -o -name "$SLUG-*.zip" \) -delete
cp "$ZIP" "$TK_APP/"
rm -rf "$(dirname "$ZIP")"
echo "== tk-tv $VERSION per Mac pubblicato: chi ce l'ha installato lo riceverà al prossimo avvio (entro 12 ore)."
