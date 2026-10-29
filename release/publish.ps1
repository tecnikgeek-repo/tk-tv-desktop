# Pubblica una versione di tk-tv per Windows: chi ce l'ha installata la riceve con l'aggiornamento automatico.
# Uso:  powershell -ExecutionPolicy Bypass -File release\publish.ps1 -Notes "Novita 1|Novita 2"
# Prerequisiti: VERSION alzata in tktv\__init__.py e commit fatto.
# Mac e Linux hanno manifest e script loro: release/publish_mac.sh e release\publish_linux.ps1.
param([Parameter(Mandatory = $true)][string]$Notes)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

# con -File PowerShell unisce piu valori in una stringa: le novita si separano con |
$noteList = @($Notes -split '\|' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$version = (Select-String -Path 'tktv\__init__.py' -Pattern 'VERSION = "(.+)"').Matches[0].Groups[1].Value
$sshConfig = 'C:\Users\TecnikGeek\Dropbox\CLAUDE\fleet\ssh-config'
$slug = 'tk-tv-player-windows'
$remoteDir = "public_html/updates/$slug"
$baseUrl = "https://pietrodefilippis.it/updates/$slug"
$manifestUrl = "https://pietrodefilippis.it/updates/$slug.json"
$tkApp = 'C:\Users\TecnikGeek\Dropbox\CLAUDE\tk-software\tk-tv\Windows'
Write-Host "== Pubblicazione tk-tv $version"

if (git status --porcelain) { throw 'Ci sono modifiche non committate: fai commit prima di pubblicare' }

# --- sicurezza: la versione non deve essere gia pubblicata
try {
    $current = Invoke-RestMethod "${manifestUrl}?t=$([DateTime]::Now.Ticks)" -TimeoutSec 15
    if ([version]$current.version -ge [version]$version) {
        throw "Sul server c'e gia la versione $($current.version): alza VERSION in tktv\__init__.py"
    }
} catch [System.Net.WebException] { Write-Host "   nessun manifest precedente (prima pubblicazione)" }

# --- pacchetti
$update = "dist\$slug-$version-update.zip"
$install = "dist\$slug-$version.zip"
if (-not (Test-Path $update) -or -not (Test-Path $install)) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File installer\build.ps1
    if ($LASTEXITCODE -ne 0) { throw 'Build fallita' }
}
# 'windows-zip' = aggiornamento automatico, 'windows-install' = ZIP di installazione per nuovi PC
$assets = @(@{ key = 'windows-zip'; file = (Resolve-Path $update).Path },
            @{ key = 'windows-install'; file = (Resolve-Path $install).Path })
# installazione .exe: e' il download «Windows» della vetrina (pietrodefilippis.it/scarica-programma/...)
$setupWin = "dist\tk-tv-setup-$version.exe"
if (-not (Test-Path $setupWin)) { throw "Manca l'installazione ${setupWin}: rifai installer\build.ps1" }
$assets += @{ key = 'windows'; file = (Resolve-Path $setupWin).Path }

# --- manifest
$manifest = [ordered]@{
    name    = 'tk-tv'
    version = $version
    date    = (Get-Date -Format 'dd/MM/yyyy')
    notes   = $noteList
}
foreach ($a in $assets) {
    $name = Split-Path $a.file -Leaf
    $manifest[$a.key] = [ordered]@{
        url    = "$baseUrl/$name"
        sha256 = (Get-FileHash $a.file -Algorithm SHA256).Hash.ToLower()
        size   = (Get-Item $a.file).Length
    }
}
$manifestFile = Join-Path $env:TEMP "$slug.json"
[IO.File]::WriteAllText($manifestFile, ($manifest | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
# firma del manifest (chiave segreta solo su questo PC): senza firma valida tk-tv non installa l'aggiornamento.
# Lo slug e' il nome del manifest (tk-tv-player-windows): e' quello che usa updater.SLUG nel programma.
& python -I "C:\Users\TecnikGeek\Dropbox\CLAUDE\tk-software\librerie\firma_aggiornamenti.py" firma --slug $slug $manifestFile
if ($LASTEXITCODE -ne 0) { throw 'Firma del manifest non riuscita: niente pubblicazione' }

# --- upload: prima i file, per ultimo il manifest (cosi nessuno scarica file mancanti)
Write-Host "   caricamento sul server..."
ssh -F $sshConfig pietrodefilippis "mkdir -p ~/$remoteDir/old"
foreach ($a in $assets) {
    scp -q -F $sshConfig $a.file "pietrodefilippis:~/$remoteDir/"
    if ($LASTEXITCODE -ne 0) { throw "Upload fallito: $($a.file)" }
}
scp -q -F $sshConfig $manifestFile "pietrodefilippis:~/public_html/updates/$slug.json.new"
# archivia le versioni precedenti (tiene solo la penultima in old/), poi attiva il manifest
$names = ($assets | ForEach-Object { Split-Path $_.file -Leaf }) -join ' '
$remote = @'
cd ~/__DIR__ && move=; for f in __SLUG__-* tk-tv-setup-*; do keep=0; for k in __NAMES__; do [ $f = $k ] && keep=1; done; [ $keep = 1 ] || move=$move' '$f; done; if [ ${#move} -gt 0 ]; then rm -f old/*; mv -f $move old/; fi; mv -f ~/public_html/updates/__SLUG__.json.new ~/public_html/updates/__SLUG__.json && ls -la ~/__DIR__ ~/__DIR__/old
'@
# NB: niente virgolette doppie nel comando remoto: PowerShell 5 le toglie passando l'argomento a ssh
$remote = $remote.Replace('__DIR__', $remoteDir).Replace('__NAMES__', $names).Replace('__SLUG__', $slug).Trim()
ssh -F $sshConfig pietrodefilippis $remote
if ($LASTEXITCODE -ne 0) { throw 'Attivazione del manifest sul server fallita' }

# --- verifica pubblica
$check = Invoke-RestMethod "${manifestUrl}?t=$([DateTime]::Now.Ticks)" -TimeoutSec 15
if ($check.version -ne $version) { throw "Il manifest pubblico non mostra $version" }
foreach ($a in $assets) {
    $url = $manifest[$a.key].url
    $resp = Invoke-WebRequest $url -Method Head -UseBasicParsing -TimeoutSec 30
    if ([int64]$resp.Headers['Content-Length'] -ne $manifest[$a.key].size) { throw "Dimensione errata online: $url" }
}
Write-Host "   manifest e file online verificati"

# --- codice sorgente di questa versione su GitHub (Informazioni > Licenze punta a .../tree/v<versione>)
$gitRemote = if (@(git remote) -contains 'github') { 'github' } else { 'origin' }
if (-not (git tag -l "v$version")) {
    git tag "v$version"
    if ($LASTEXITCODE -ne 0) { throw "Creazione del tag v$version non riuscita" }
}
git push $gitRemote "v$version"
if ($LASTEXITCODE -ne 0) { throw "Invio del tag v$version a GitHub non riuscito" }

# --- cartella tk-app di Dropbox: solo l'ultima versione
Get-ChildItem $tkApp -Filter "$slug-*.zip" | Where-Object { $_.Name -ne "$slug-$version.zip" } | Remove-Item -Force
Get-ChildItem $tkApp -Filter 'tk-tv-setup-*.exe' | Where-Object { $_.Name -ne "tk-tv-setup-$version.exe" } | Remove-Item -Force
Copy-Item $install, "dist\tk-tv-setup-$version.exe" $tkApp -Force
Write-Host "== tk-tv $version pubblicato: chi ce l'ha installato lo ricevera al prossimo avvio (entro 12 ore)."
