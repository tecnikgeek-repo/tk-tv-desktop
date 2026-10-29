# Pubblica tk-tv per Linux: chi ce l'ha la riceve con l'aggiornamento automatico (manifest tk-tv-player-linux.json).
# Uso:  powershell -ExecutionPolicy Bypass -File release\publish_linux.ps1 -Notes "Novita 1|Novita 2"
# Prerequisiti: VERSION alzata in tktv\__init__.py, commit fatto e inviato su main (la build gira su GitHub dal main:
# .github\workflows\build-linux.yml crea l'AppImage, lo collauda e lo mette nella release v<versione>).
# Windows (release\publish.ps1) e Mac (release/publish_mac.sh) hanno i loro manifest: si pubblicano a parte.
param([Parameter(Mandatory = $true)][string]$Notes)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

# con -File PowerShell unisce piu valori in una stringa: le novita si separano con |
$noteList = @($Notes -split '\|' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$version = (Select-String -Path 'tktv\__init__.py' -Pattern 'VERSION = "(.+)"').Matches[0].Groups[1].Value
$repo = 'tecnikgeek-repo/tk-tv-desktop'
$sshConfig = Join-Path $env:USERPROFILE 'Dropbox\CLAUDE\fleet\ssh-config'
$firma = Join-Path $env:USERPROFILE 'Dropbox\CLAUDE\tk-software\librerie\firma_aggiornamenti.py'
$slug = 'tk-tv-player-linux'
$remoteDir = "public_html/updates/$slug"
$baseUrl = "https://pietrodefilippis.it/updates/$slug"
$manifestUrl = "https://pietrodefilippis.it/updates/$slug.json"
$tkApp = Join-Path $env:USERPROFILE 'Dropbox\CLAUDE\tk-software\tk-tv\Linux'
$appName = "$slug-$version-x86_64.AppImage"
Write-Host "== Pubblicazione tk-tv $version per Linux"

if (git status --porcelain) { throw 'Ci sono modifiche non committate: fai commit prima di pubblicare' }
git fetch -q origin main
if ($LASTEXITCODE -ne 0) { throw 'git fetch non riuscito' }
$sha = (git rev-parse HEAD).Trim()
if ($sha -ne (git rev-parse origin/main).Trim()) { throw 'Il commit da pubblicare deve essere su main su GitHub (git push origin main)' }

# --- sicurezza: la versione non deve essere gia pubblicata
try {
    $current = Invoke-RestMethod "${manifestUrl}?t=$([DateTime]::Now.Ticks)" -TimeoutSec 15
    if ([version]$current.version -ge [version]$version) {
        throw "Sul server c'e gia la versione $($current.version) per Linux: alza VERSION in tktv\__init__.py"
    }
} catch [System.Net.WebException] { Write-Host '   nessun manifest Linux precedente (prima pubblicazione)' }

# --- build su GitHub (ubuntu-22.04): AppImage + selftest video + test aggiornamento firmato
gh workflow run build-linux.yml --repo $repo --ref main
if ($LASTEXITCODE -ne 0) { throw 'Avvio della build Linux su GitHub non riuscito' }
Start-Sleep -Seconds 5
$runId = $null
for ($i = 0; $i -lt 30 -and -not $runId; $i++) {
    $runId = gh run list --repo $repo --workflow build-linux.yml --commit $sha --event workflow_dispatch --json databaseId --jq '.[0].databaseId'
    if (-not $runId) { Start-Sleep -Seconds 5 }
}
if (-not $runId) { throw 'Build Linux non trovata su GitHub' }
Write-Host "   attendo la build Linux del commit $($sha.Substring(0,7))..."
gh run watch $runId --repo $repo --exit-status | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Build Linux fallita: https://github.com/$repo/actions/runs/$runId" }

$linuxDir = Join-Path $root "dist\linux-$version"
if (Test-Path $linuxDir) { Remove-Item -LiteralPath $linuxDir -Recurse -Force }
New-Item -ItemType Directory -Force $linuxDir | Out-Null
gh release download "v$version" --repo $repo --dir $linuxDir --pattern '*.AppImage' --clobber
if ($LASTEXITCODE -ne 0) { throw "Download dell'AppImage dalla release v$version fallito" }
$appImage = Join-Path $linuxDir $appName
if (-not (Test-Path $appImage)) { throw "Manca $appName nella release v$version" }

# --- manifest (chiave linux-x86_64)
$manifest = [ordered]@{
    name    = 'tk-tv'
    version = $version
    date    = (Get-Date -Format 'dd/MM/yyyy')
    notes   = $noteList
}
$manifest['linux-x86_64'] = [ordered]@{
    url    = "$baseUrl/$appName"
    sha256 = (Get-FileHash $appImage -Algorithm SHA256).Hash.ToLower()
    size   = (Get-Item $appImage).Length
}
$manifestFile = Join-Path $env:TEMP "$slug.json"
[IO.File]::WriteAllText($manifestFile, ($manifest | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
# firma del manifest (chiave segreta solo su questo PC): senza firma valida tk-tv non installa l'aggiornamento.
# Lo slug e' il nome del manifest (tk-tv-player-linux): e' quello che usa updater.SLUG nel programma.
& python -I $firma firma --slug $slug $manifestFile
if ($LASTEXITCODE -ne 0) { throw 'Firma del manifest non riuscita: niente pubblicazione' }

# --- upload: prima il file, per ultimo il manifest (cosi nessuno scarica file mancanti)
Write-Host '   caricamento sul server...'
ssh -F $sshConfig pietrodefilippis "mkdir -p ~/$remoteDir/old"
if ($LASTEXITCODE -ne 0) { throw 'Collegamento al server non riuscito' }
scp -q -F $sshConfig $appImage "pietrodefilippis:~/$remoteDir/"
if ($LASTEXITCODE -ne 0) { throw "Upload fallito: $appName" }
scp -q -F $sshConfig $manifestFile "pietrodefilippis:~/public_html/updates/$slug.json.new"
if ($LASTEXITCODE -ne 0) { throw 'Upload del manifest fallito' }
# archivia le versioni precedenti (tiene solo la penultima in old/), poi attiva il manifest
$remote = @'
cd ~/__DIR__ && move=; for f in __SLUG__-*; do [ $f = __NAME__ ] || move=$move' '$f; done; if [ ${#move} -gt 0 ]; then rm -f old/*; mv -f $move old/; fi; chmod 644 __NAME__ ~/public_html/updates/__SLUG__.json.new && mv -f ~/public_html/updates/__SLUG__.json.new ~/public_html/updates/__SLUG__.json && ls -la ~/__DIR__ ~/__DIR__/old
'@
# NB: niente virgolette doppie nel comando remoto: PowerShell 5 le toglie passando l'argomento a ssh
$remote = $remote.Replace('__DIR__', $remoteDir).Replace('__NAME__', $appName).Replace('__SLUG__', $slug).Trim()
ssh -F $sshConfig pietrodefilippis $remote
if ($LASTEXITCODE -ne 0) { throw 'Attivazione del manifest sul server fallita' }

# --- verifica pubblica
$check = Invoke-RestMethod "${manifestUrl}?t=$([DateTime]::Now.Ticks)" -TimeoutSec 15
if ($check.version -ne $version) { throw "Il manifest pubblico non mostra $version" }
$resp = Invoke-WebRequest $manifest['linux-x86_64'].url -Method Head -UseBasicParsing -TimeoutSec 30
if ([int64]$resp.Headers['Content-Length'] -ne $manifest['linux-x86_64'].size) { throw "Dimensione errata online: $appName" }
Write-Host '   manifest e file online verificati'

# --- codice sorgente di questa versione su GitHub (la build da main ha gia creato la release v<versione>)
git fetch -q --tags origin
if (-not (git tag -l "v$version")) {
    git tag "v$version"
    if ($LASTEXITCODE -ne 0) { throw "Creazione del tag v$version non riuscita" }
    git push origin "v$version"
    if ($LASTEXITCODE -ne 0) { throw "Invio del tag v$version a GitHub non riuscito" }
}

# --- cartella tk-software di Dropbox: Linux\ con solo l'ultima versione e il leggimi
New-Item -ItemType Directory -Force $tkApp | Out-Null
Get-ChildItem $tkApp -File | Where-Object { $_.Name -like "$slug-*" -and $_.Name -ne $appName } | Remove-Item -Force
Copy-Item $appImage $tkApp -Force
Copy-Item (Join-Path $root 'linux\LEGGIMI.txt') (Join-Path $tkApp 'Leggimi - installazione.txt') -Force
Write-Host "== tk-tv $version per Linux pubblicato: chi ce l'ha installato lo ricevera al prossimo avvio (entro 12 ore)."
