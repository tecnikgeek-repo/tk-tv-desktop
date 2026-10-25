# Crea i pacchetti di tk-tv per Windows in dist\
#   tk-tv-player-windows-<ver>.zip          ZIP di installazione (cartella con «Installa tk-tv.cmd» + app\)
#   tk-tv-player-windows-<ver>-update.zip   pacchetto per l'aggiornamento automatico (contenuto di app\)
# Contengono: runtime Python ridotto + PySide6 (solo moduli usati) + libVLC ridotta + tk-tv + testi delle licenze.
# Niente exe nuovi: tutto parte da pythonw.exe (copiato come tk-tv.exe), già noto a Smart App Control.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$version = (Select-String -Path 'tktv\__init__.py' -Pattern 'VERSION = "(.+)"').Matches[0].Groups[1].Value
$stageRoot = Join-Path $env:TEMP 'tktv-stage'
$stage = Join-Path $stageRoot 'app'
$dist = Join-Path $root 'dist'
Write-Host "== tk-tv ${version} - preparazione file"

if (Test-Path $stageRoot) { Remove-Item $stageRoot -Recurse -Force }
New-Item -ItemType Directory -Force $stage | Out-Null
New-Item -ItemType Directory -Force $dist | Out-Null

function Robo($src, $dst, [string[]]$extra) {
    & robocopy $src $dst /E /NFL /NDL /NJH /NJS /NP @extra | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy fallito ($LASTEXITCODE): $src" }
}

# --- runtime Python (interprete di base del venv: quello del venv è bloccato da Smart App Control)
$homeLine = Get-Content '.venv\pyvenv.cfg' | Where-Object { $_ -match '^home\s*=' }
$pyHome = ($homeLine -replace '^home\s*=\s*', '').Trim()
$hostPy = Join-Path $pyHome 'python.exe'
$py = Join-Path $stage 'python'
Robo $pyHome $py @('/XD', 'test', 'tests', 'idlelib', 'tkinter', 'turtledemo', 'tcl', 'include', 'libs', 'Scripts',
                   'ensurepip', 'lib2to3', 'site-packages', '__phello__', 'pydoc_data', 'sqlite3',
                   '/XF', '*.pdb', '_tkinter.pyd', 'tcl*.dll', 'tk*.dll', 'EXTERNALLY-MANAGED', '_sqlite3.pyd', 'sqlite3.dll')
# tk-tv.exe = copia identica di pythonw.exe: in Gestione attività si vede il nome dell'app e, essendo lo stesso file,
# Smart App Control lo accetta come pythonw.exe (NON modificarne icona o dati: cambierebbe il file).
# pythonw.exe resta: gli aggiornamenti dalle versioni <= 1.0.8 lo cercano e lo riavviano.
Copy-Item "$py\pythonw.exe" "$py\tk-tv.exe"
if ((Get-FileHash "$py\pythonw.exe").Hash -ne (Get-FileHash "$py\tk-tv.exe").Hash) { throw 'tk-tv.exe diverso da pythonw.exe' }
# python.exe (console) all'app non serve: la build precompila con l'interprete di sviluppo ($hostPy)
Remove-Item "$py\python.exe"

# --- librerie Python
$sp = '.venv\Lib\site-packages'
$dsp = Join-Path $py 'Lib\site-packages'
New-Item -ItemType Directory -Force $dsp | Out-Null
Robo "$sp\shiboken6" "$dsp\shiboken6" @()
Robo "$sp\certifi" "$dsp\certifi" @()
Copy-Item "$sp\vlc.py" $dsp

$ps = "$sp\PySide6"
$dps = "$dsp\PySide6"
New-Item -ItemType Directory -Force $dps | Out-Null
$files = @('pyside6.abi3.dll', 'QtCore.pyd', 'QtGui.pyd', 'QtWidgets.pyd', 'QtNetwork.pyd',
           'Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll', 'Qt6Network.dll', 'Qt6Svg.dll')
Get-ChildItem $ps -File | Where-Object {
    $_.Extension -eq '.py' -or $files -contains $_.Name -or $_.Name -match '^(msvcp140|vcruntime140|concrt140)'
} | ForEach-Object { Copy-Item $_.FullName $dps }
foreach ($plug in @('platforms\qwindows.dll', 'styles\qmodernwindowsstyle.dll', 'iconengines\qsvgicon.dll',
                    'imageformats\qjpeg.dll', 'imageformats\qgif.dll', 'imageformats\qico.dll',
                    'imageformats\qsvg.dll', 'imageformats\qwebp.dll', 'tls\qschannelbackend.dll')) {
    $srcp = Join-Path "$ps\plugins" $plug
    if (Test-Path $srcp) {
        $dstp = Join-Path "$dps\plugins" $plug
        New-Item -ItemType Directory -Force (Split-Path $dstp) | Out-Null
        Copy-Item $srcp $dstp
    }
}
New-Item -ItemType Directory -Force "$dps\translations" | Out-Null
Copy-Item "$ps\translations\qtbase_it.qm" "$dps\translations\" -ErrorAction SilentlyContinue

# --- libVLC (firmata VideoLAN) dallo ZIP ufficiale, con l'impronta SHA-256 controllata (come su Mac)
$vlcVer = '3.0.24'
$vlcSha = 'fcf30850371ad10c9373cc4f0f4501e7dee49e3e9ae9f20c72fb2661a1ca6323'  # vlc-3.0.24-win64.zip, da videolan.org
$vlcZip = 'vendor\vlc.zip'
if (-not (Test-Path $vlcZip)) {
    New-Item -ItemType Directory -Force 'vendor' | Out-Null
    Write-Host "   scarico VLC $vlcVer da videolan.org..."
    Invoke-WebRequest "https://get.videolan.org/vlc/$vlcVer/win64/vlc-$vlcVer-win64.zip" -OutFile $vlcZip -UseBasicParsing
}
if ((Get-FileHash $vlcZip -Algorithm SHA256).Hash.ToLower() -ne $vlcSha) {
    throw "vendor\vlc.zip non e' lo ZIP ufficiale di VLC $vlcVer (impronta SHA-256 diversa): cancellalo e riprova"
}
# estratto ogni volta in una cartella nuova: nel pacchetto finisce solo ciò che sta nello ZIP verificato
$vlcExtract = Join-Path $stageRoot 'vlc-ufficiale'
New-Item -ItemType Directory -Force $vlcExtract | Out-Null
& tar -xf $vlcZip -C $vlcExtract
if ($LASTEXITCODE -ne 0) { throw 'Estrazione di vendor\vlc.zip fallita' }
$vlcSrc = Get-Item (Join-Path $vlcExtract "vlc-$vlcVer")
$vlc = Join-Path $stage 'vlc'
New-Item -ItemType Directory -Force $vlc | Out-Null
Copy-Item "$($vlcSrc.FullName)\libvlc.dll", "$($vlcSrc.FullName)\libvlccore.dll" $vlc
Robo "$($vlcSrc.FullName)\plugins" "$vlc\plugins" @('/XF', 'plugins.dat', '*.jar')
# solo i plugin che servono a guardare i flussi di rete (come fa il Mac): quelli che libVLC carica davvero
# (engine.WIN_HOT, misurati su tutti i canali) più sottotitoli, conversioni audio/video e uscite di riserva.
# Fuori: encoder (x264, x265), DVD e Blu-ray, sid, aribcam, postproc e gli accessi locali o di rete
# non da TV (smb, nfs, sftp, ftp, dshow, screen, vnc, dtv…).
$keep = @'
filesystem http https live555 udp rtp tcp
adf archive cache_block cache_read hds inflate prefetch record skiptags
adaptive asf avi caf diracsys directory_demux dmxmus es flacsys gme h26x mkv mp4 mpc mpgv nuv ogg playlist ps
smf ts tta wav xa
aes3 aom araw avcodec cc cdg cvdsub d3d11va dav1d dvbsub dxva2 faad flac fluidsynth g711 jpeg lpcm mpg123 opus
png rawvideo scte27 spdif speex spudec stl subsdec substx3g subsusf svcdsub theora ttml vorbis webvtt zvbi
packetizer_*
audio_format dolby_surround_decoder headphone_channel_mixer remap samplerate scaletempo simple_channel_mixer
speex_resampler tospdif trivial_channel_mixer ugly_resampler float_mixer integer_mixer
mmdevice wasapi directsound waveout adummy
chain grey_yuv i420_* i422_* rv32 swscale yuvp yuy2_*
blend deinterlace scale direct3d11_filters direct3d9_filters
direct3d11 direct3d9 drawable gl glinterop_dxva2 glwin32 wgl wingdi winhibit vdummy
freetype tdummy
console_logger file_logger logger gnutls memory_keystore xml
'@ -split '\s+' | Where-Object { $_ }
$dropped = 0
Get-ChildItem "$vlc\plugins" -Recurse -File -Filter '*.dll' | ForEach-Object {
    $n = $_.Name -replace '^lib', '' -replace '_plugin\.dll$', ''
    $ok = $false
    foreach ($k in $keep) { if ($n -like $k) { $ok = $true; break } }
    if (-not $ok) { Remove-Item $_.FullName -Force; $dropped++ }
}
Get-ChildItem "$vlc\plugins" -Directory | Where-Object { -not (Get-ChildItem $_.FullName -Recurse -File) } |
    Remove-Item -Recurse -Force
foreach ($n in @('x264', 'x26410b', 'x265', 'dvdnav', 'dvdread', 'sid', 'aribcam', 'postproc', 'smb', 'dshow',
                 'screen', 'vnc', 'sftp', 'nfs')) {
    if (Get-ChildItem "$vlc\plugins" -Recurse -File -Filter "lib${n}_plugin.dll") { throw "Plugin VLC da togliere ancora presente: $n" }
}
$kept = @(Get-ChildItem "$vlc\plugins" -Recurse -File -Filter '*.dll').Count
Write-Host "   plugin VLC inclusi: $kept (tolti $dropped)"
# lo ZIP salva le date a 2 secondi: un plugin con i secondi dispari, una volta installato, risulta «modificato»
# e libVLC lo ricarica a ogni avvio (141 plugin su 297, ~12 s al primo canale dopo un riavvio). Date arrotondate
# al secondo pari PRIMA di creare l'indice, così sopravvivono allo ZIP.
function EvenSeconds($items) {
    $items | ForEach-Object {
        $t = $_.LastWriteTime
        $_.LastWriteTime = $t.Date.AddHours($t.Hour).AddMinutes($t.Minute).AddSeconds($t.Second - ($t.Second % 2))
    }
}
EvenSeconds (Get-ChildItem $vlc -Recurse -File)
# indice dei plugin: senza, libVLC li scansiona tutti a ogni avvio
& "$($vlcSrc.FullName)\vlc-cache-gen.exe" "$vlc\plugins"
if (-not (Test-Path "$vlc\plugins\plugins.dat")) { throw 'vlc-cache-gen non ha creato plugins.dat' }
EvenSeconds (Get-Item "$vlc\plugins\plugins.dat")  # la sua data a libVLC non interessa: solo per il controllo dopo lo ZIP

# --- applicazione
Robo 'tktv' "$stage\tktv" @('/XD', '__pycache__')
New-Item -ItemType Directory -Force "$stage\assets" | Out-Null
Copy-Item 'assets\tk-tv.ico', 'assets\tecnikgeek-logo.png' "$stage\assets"
Copy-Item 'run.py' $stage
# --- testi delle licenze (AGPL di tk-tv + componenti inclusi), accanto a run.py: Informazioni > Licenze
& $hostPy -I installer\licenze.py "$stage\licenze" --site $sp --vlc $vlcSrc.FullName --python-licenza "$pyHome\LICENSE.txt"
if ($LASTEXITCODE -ne 0) { throw 'Creazione della cartella licenze fallita' }
foreach ($f in @('COPYING-AGPL-3.0.txt', 'COMPONENTI.txt', 'VLC-COPYING.txt', 'LGPL-2.1.txt', 'GPL-2.0.txt', 'LGPL-3.0.txt',
                 'Python-PSF.txt')) {
    if (-not (Test-Path "$stage\licenze\$f")) { throw "Manca licenze\$f" }
}

# --- precompila i .py (avvio più rapido)
& $hostPy -m compileall -q "$py\Lib" 2>$null | Out-Null
# il codice di tk-tv va nel pacchetto SOLO compilato: .pyc accanto ai moduli (-b), sorgenti tolti
& $hostPy -m compileall -q -b "$stage\tktv" 2>$null | Out-Null
Get-ChildItem "$stage\tktv" -Recurse -File -Filter '*.py' | Remove-Item -Force
Get-ChildItem "$stage\tktv" -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
if (Get-ChildItem "$stage\tktv" -Recurse -File -Filter '*.py') { throw 'Nel pacchetto sono rimasti dei sorgenti .py' }

# --- verifica: avvio reale dal runtime ridotto (interfaccia + libVLC)
$shot = Join-Path $stageRoot 'selftest.png'
$p = Start-Process "$py\tk-tv.exe" -ArgumentList "`"$stage\run.py`"", '--selftest', "`"$shot`"" -PassThru
if (-not $p.WaitForExit(60000)) { Stop-Process -Id $p.Id -Force; throw 'Selftest in timeout' }
if (Test-Path "$shot.err") { throw "Selftest: libVLC non parte - $(Get-Content "$shot.err")" }
if (-not (Test-Path $shot)) { throw 'Selftest fallito: il runtime ridotto non avvia tk-tv' }
Remove-Item $shot
Write-Host "   selftest runtime OK (interfaccia + libVLC)"

$zipCode = "import os,sys,zipfile`nsrc,dst=sys.argv[1],sys.argv[2]`nwith zipfile.ZipFile(dst,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:`n  for d,_,fs in os.walk(src):`n    for f in fs:`n      p=os.path.join(d,f); z.write(p, os.path.relpath(p,src).replace(os.sep,'/'))"

# --- pacchetto di aggiornamento (lo estrae tar.exe di sistema: percorsi con /)
$updateZip = Join-Path $dist "tk-tv-player-windows-$version-update.zip"
& $hostPy -c $zipCode $stage $updateZip
if ($LASTEXITCODE -ne 0) { throw 'Creazione ZIP di aggiornamento fallita' }
# controllo: estratto come fa l'aggiornamento (tar), ogni file di VLC deve avere la stessa data dell'indice plugins.dat
$check = Join-Path $stageRoot 'verifica-zip'
New-Item -ItemType Directory -Force $check | Out-Null
& tar -xf $updateZip -C $check 'vlc/*'
$stageLong = (Get-Item $stage).FullName  # $env:TEMP può essere in forma corta (TECNIK~1)
$checkLong = (Get-Item $check).FullName
$stale = @(Get-ChildItem "$stageLong\vlc" -Recurse -File | Where-Object {
    $x = Get-Item ($checkLong + $_.FullName.Substring($stageLong.Length)) -ErrorAction SilentlyContinue
    -not $x -or $x.LastWriteTimeUtc -ne $_.LastWriteTimeUtc })
Remove-Item $check -Recurse -Force
if ($stale.Count) { throw "Dopo l'estrazione $($stale.Count) file di VLC hanno un'altra data (es. $($stale[0].Name)): plugins.dat non varrebbe" }
Write-Host "   date dei plugin VLC intatte dopo lo ZIP (indice valido)"

# --- ZIP di installazione senza exe (niente blocchi di antivirus / Smart App Control)
$installRoot = Join-Path $stageRoot 'installa'
$installDir = Join-Path $installRoot "tk-tv-$version"  # cartella che vede chi estrae lo ZIP
New-Item -ItemType Directory -Force $installDir | Out-Null
Robo $stage "$installDir\app" @()
$cmdText = Get-Content "$PSScriptRoot\Installa tk-tv.cmd" -Raw
[IO.File]::WriteAllText("$installDir\Installa tk-tv.cmd", ($cmdText -replace "`r?`n", "`r`n"), [Text.Encoding]::ASCII)
$readme = Get-Content "$PSScriptRoot\Leggimi-zip.txt" -Raw -Encoding UTF8
[IO.File]::WriteAllText("$installDir\Leggimi.txt", ($readme -replace "`r?`n", "`r`n"), (New-Object Text.UTF8Encoding($true)))
$installZip = Join-Path $dist "tk-tv-player-windows-$version.zip"
& $hostPy -c $zipCode $installRoot $installZip
if ($LASTEXITCODE -ne 0) { throw 'Creazione ZIP di installazione fallita' }

# --- installer exe (stesso modello di tk-pdf: setup.cs = strumenti\tk-setup.cs); contiene il pacchetto di aggiornamento
$csc = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$sizeKb = [int]((Get-ChildItem $stage -Recurse -File | Measure-Object Length -Sum).Sum / 1KB)
$map = [ordered]@{
    NAME = 'tk-tv'
    SLUG = 'tk-tv-player'
    TAGLINE = 'la TV in diretta della tua playlist M3U'
    SUBDIR = ''
    DATADIR = ''
    ICON = 'tk-tv.ico'
    ACCENT = '#e11d48'
    UNINSTALL = 'app'
    UNINSTALLKEY = 'tk-tv-player'
    LNK = 'tk-tv'
    LEGACYLNK = 'TK TV;tkTV'
    LAUNCHSCHEMA = '4'
    ITEMS = 'python;tktv;assets;vlc;licenze'
    VERSION = $version
    SIZEKB = "$sizeKb"
}
$setupSrc = Get-Content "$PSScriptRoot\setup.cs" -Raw -Encoding UTF8
foreach ($k in $map.Keys) { $setupSrc = $setupSrc.Replace("@@$k@@", [string]$map[$k]) }
$genSrc = Join-Path $stageRoot 'setup.cs'
[IO.File]::WriteAllText($genSrc, $setupSrc, (New-Object Text.UTF8Encoding($true)))
$setupExe = Join-Path $dist "tk-tv-setup-$version.exe"
& $csc /nologo /optimize+ /target:winexe /platform:anycpu /win32icon:"$root\assets\tk-tv.ico" `
    /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Core.dll `
    /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll `
    /resource:"$updateZip",payload.zip /out:"$setupExe" $genSrc
if ($LASTEXITCODE -ne 0) { throw 'Compilazione installer fallita' }
Write-Host "   installer: $setupExe ($([math]::Round((Get-Item $setupExe).Length/1MB,1)) MB)"

$sizeMb = [math]::Round((Get-ChildItem $stage -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
Remove-Item $stageRoot -Recurse -Force
$mb = [math]::Round((Get-Item $installZip).Length / 1MB, 1)
Write-Host "== Creato $installZip ($mb MB, installato $sizeMb MB)"
