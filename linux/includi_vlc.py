"""libVLC per l'AppImage di tk-tv, presa dai pacchetti Ubuntu (VideoLAN non distribuisce una libVLC portabile per
Linux). Solo libreria standard; da eseguire su Ubuntu (runner ubuntu-22.04 o PC di casa) senza installare niente:
i pacchetti si scaricano con «apt-get download» e si aprono con «dpkg-deb -x».

Uso:
  python3 -I linux/includi_vlc.py vlc <cartella_vlc> <cartella_lavoro> <cartella_licenze> <cartella_qt_xcb>
  python3 -I linux/includi_vlc.py controlla <cartella>

«vlc»: scarica libvlc5, libvlccore9, vlc-plugin-base, vlc-plugin-video-output (e libvlc-bin per vlc-cache-gen) con
le loro dipendenze, poi copia in <cartella_vlc>:
  lib/      libvlc.so.5, libvlccore.so.9, le librerie private di VLC e le librerie che servono e NON sono «di base»
  plugins/  solo i plugin che servono a un lettore di flussi di rete (elenco PLUGIN), con la cache plugins.dat
Tutti i file ricevono RUNPATH relativo ($ORIGIN): cercano le librerie prima nel pacchetto e mai in un VLC del sistema.
Le librerie «di base» (SISTEMA: glibc, OpenGL, X11, Wayland, audio, GLib/GTK, font…) restano quelle del sistema,
come fa linuxdeploy: ci sono su ogni Ubuntu desktop con lo stesso nome dalla 22.04 in poi.
In <cartella_qt_xcb> mette le librerie xcb che servono a Qt sotto X11/XWayland e che non tutti gli Ubuntu hanno
(libxcb-cursor…): il .spec le mette accanto alle librerie di Qt.
In <cartella_licenze> copia i file copyright dei pacchetti usati e scrive LINUX-PACCHETTI.txt (pacchetto, versione,
file inclusi).

«controlla»: ldd su ogni libreria e programma della cartella (con le librerie del pacchetto davanti): esce con
errore se manca una libreria che non è «di base». Elenca le librerie di base richieste.
"""
import fnmatch
import glob
import os
import re
import shutil
import struct
import subprocess
import sys

PACCHETTI_VLC = ["libvlc5", "libvlccore9", "vlc-plugin-base", "vlc-plugin-video-output", "libvlc-bin"]
PACCHETTI_QT_XCB = ["libxcb-cursor0", "libxcb-icccm4", "libxcb-image0", "libxcb-keysyms1", "libxcb-render-util0",
                    "libxcb-util1", "libxkbcommon-x11-0", "libxcb-xinerama0", "libxcb-xinput0"]
# librerie di Qt sotto X11 da mettere nel pacchetto (le altre xcb sono di base)
SO_QT_XCB = ["libxcb-cursor.so.0", "libxcb-icccm.so.4", "libxcb-image.so.0", "libxcb-keysyms.so.1",
             "libxcb-render-util.so.0", "libxcb-util.so.1", "libxkbcommon-x11.so.0", "libxcb-xinerama.so.0",
             "libxcb-xinput.so.0"]

# Plugin VLC tenuti (nome senza «lib» e «_plugin.so»): flussi di rete (http/https/udp/rtp/rtsp/rtmp, HLS e DASH),
# demuxer e decoder dei canali TV, sottotitoli, uscite video X11/OpenGL (finestra incorporata con set_xwindow),
# uscite audio PulseAudio/PipeWire e ALSA, più le uscite «finte» usate dal selftest senza schermo.
PLUGIN = """
filesystem http https udp rtp tcp live555 sdp
adaptive hds prefetch cache_read cache_block inflate skiptags
ts es mp4 mkv ogg playlist ps wav h26x flacsys mpgv subtitle vobsub xml
avcodec faad mpg123 opus vorbis flac speex lpcm araw g711 aes3 spdif a52 dca theora dav1d rawvideo
subsdec subsusf cc zvbi telx dvbsub scte18 scte27 spudec cvdsub svcdsub substx3g webvtt ttml stl jpeg png
packetizer_* i420_* i422_* yuy2_* grey_yuv rv32 chain swscale yuvp
xcb_window xcb_x11 xcb_xv gl glx egl_x11 vdummy
deinterlace scale blend
pulse alsa adummy float_mixer integer_mixer samplerate scaletempo audio_format trivial_channel_mixer
simple_channel_mixer remap ugly_resampler speex_resampler soxr dolby_surround_decoder headphone_channel_mixer tospdif
freetype tdummy gnutls memory_keystore console_logger file_logger
""".split()

# Pacchetti «di base»: non si scaricano e non si seguono le loro dipendenze
PKG_BASE = [r"libc6", r"libc-bin", r"libgcc-s1", r"libstdc\+\+6", r"zlib1g", r"libglib2\.0-0(t64)?", r"libdbus-1-3",
            r"libsystemd0", r"libudev1", r"libx11-.*", r"libx11-6", r"libxcb1", r"libxcb-(dri2|dri3|present|glx|sync|"
            r"xfixes|randr|shm|render|shape|xkb)0", r"libxcb-xkb1", r"libxcb-dri3-0", r"libxcb-glx0", r"libxcb-sync1",
            r"libxcb-randr0", r"libxcb-shm0", r"libxcb-render0", r"libxcb-shape0", r"libxcb-xfixes0",
            r"libxcb-present0", r"libxcb-dri2-0", r"libx(ext|render|fixes|i|randr|cursor|inerama|au|dmcp|xf86vm|damage|"
            r"composite|shmfence|v)[0-9]+", r"libxshmfence1", r"libxkbcommon0", r"libgl1.*", r"libegl.*", r"libgles.*",
            r"libglx.*", r"libopengl0", r"libglvnd0", r"libgbm1", r"libdrm.*", r"libvulkan1", r"mesa-.*",
            r"libllvm.*", r"libwayland-.*", r"libasound2.*", r"libpulse0", r"libpulse-.*", r"libjack.*",
            r"libpipewire.*", r"libfontconfig1", r"fontconfig-config", r"libfreetype6", r"libharfbuzz0b",
            r"libfribidi0", r"libpng16-16(t64)?", r"libexpat1", r"libbz2-1\.0", r"liblzma5", r"libzstd1", r"liblz4-1",
            r"libjpeg8", r"libjpeg-turbo8", r"libcairo.*", r"libpango.*", r"libgdk-pixbuf.*", r"librsvg2-.*",
            r"libgtk.*", r"libatk.*", r"libpixman-1-0", r"libselinux1", r"libpcre2-.*", r"libpcre3", r"libffi8",
            r"libgcrypt20", r"libgpg-error0", r"libuuid1", r"libblkid1", r"libmount1", r"libcap2", r"libapparmor1",
            r"libgnutls30(t64)?", r"libp11-kit0", r"libtasn1-6", r"libnettle8(t64)?", r"libhogweed6(t64)?",
            r"libgmp10", r"libidn2-0", r"libssl3(t64)?", r"libgssapi-krb5-2", r"libkrb5.*", r"libk5crypto3",
            r"libcom-err2", r"libkeyutils1", r"libavahi-.*", r"libsqlite3-0", r"debconf.*", r"dpkg", r"perl.*",
            r"libcrypt1", r"libsndfile1", r"libdb5\.3.*", r"libwrap0", r"libasyncns0", r"libltdl7", r"libelf1.*",
            r"libtinfo6", r"libncurses.*", r"libsystemd-shared", r"adduser", r"passwd", r"init-system-helpers",
            r"libsensors.*", r"libpciaccess0", r"libedit2", r"libdconf1", r"dconf-.*",
            r"libgdk-pixbuf2.0-common", r"shared-mime-info", r"hicolor-icon-theme", r"adwaita-icon-theme",
            r"gtk-update-icon-cache", r"libthai.*", r"libdatrie1", r"libgraphite2-3", r"libbrotli1", r"libcolord2",
            r"libcups2", r"libepoxy0", r"libatspi2.*", r"libcloudproviders0", r"libtracker.*"]

# Librerie «di base» (nome .so): restano quelle del sistema (ci sono su ogni Ubuntu desktop dalla 22.04)
SO_BASE = [r"ld-linux.*", r"libc\.so\..*", r"libm\.so\..*", r"libdl\.so\..*", r"libpthread\.so\..*", r"librt\.so\..*",
           r"libutil\.so\..*", r"libresolv\.so\..*", r"libanl\.so\..*", r"libnsl\.so\..*", r"libmvec\.so\..*",
           r"libcrypt\.so\.1", r"libgcc_s\.so\.1", r"libstdc\+\+\.so\.6",
           r"libGL\.so\.1", r"libGLX\.so\.0", r"libEGL\.so\.1", r"libOpenGL\.so\.0", r"libGLdispatch\.so\.0",
           r"libGLESv2\.so\.2", r"libgbm\.so\.1", r"libdrm\.so\.2", r"libvulkan\.so\.1",
           r"libX11\.so\.6", r"libX11-xcb\.so\.1", r"libxcb\.so\.1",
           r"libxcb-(dri2|dri3|present|glx|sync|xfixes|randr|shm|render|shape|xkb)\.so\..*",
           r"libX(ext|render|fixes|i|randr|cursor|inerama|au|dmcp|xf86vm|damage|composite|v)\.so\..*",
           r"libxshmfence\.so\.1", r"libxkbcommon\.so\.0", r"libwayland-(client|cursor|egl|server)\.so\.[01]",
           r"libasound\.so\.2", r"libpulse\.so\.0", r"libpulse-simple\.so\.0", r"libpulse-mainloop-glib\.so\.0",
           r"libjack\.so\.0", r"libpipewire-0\.3\.so\.0",
           r"libfontconfig\.so\.1", r"libfreetype\.so\.6", r"libharfbuzz\.so\.0", r"libfribidi\.so\.0",
           r"libpng16\.so\.16", r"libz\.so\.1", r"libexpat\.so\.1", r"libbz2\.so\.1\.0", r"liblzma\.so\.5",
           r"libzstd\.so\.1", r"liblz4\.so\.1", r"libjpeg\.so\.8",
           r"libglib-2\.0\.so\.0", r"libgobject-2\.0\.so\.0", r"libgio-2\.0\.so\.0", r"libgmodule-2\.0\.so\.0",
           r"libgthread-2\.0\.so\.0", r"libcairo\.so\.2", r"libcairo-gobject\.so\.2", r"libpango-1\.0\.so\.0",
           r"libpangocairo-1\.0\.so\.0", r"libpangoft2-1\.0\.so\.0", r"libgdk_pixbuf-2\.0\.so\.0", r"librsvg-2\.so\.2",
           r"libgtk-3\.so\.0", r"libgdk-3\.so\.0", r"libatk-1\.0\.so\.0", r"libpixman-1\.so\.0",
           r"libdbus-1\.so\.3", r"libsystemd\.so\.0", r"libudev\.so\.1", r"libselinux\.so\.1", r"libpcre2-8\.so\.0",
           r"libffi\.so\.8", r"libgcrypt\.so\.20", r"libgpg-error\.so\.0", r"libuuid\.so\.1", r"libblkid\.so\.1",
           r"libmount\.so\.1", r"libcap\.so\.2", r"libapparmor\.so\.1",
           r"libgnutls\.so\.30", r"libp11-kit\.so\.0", r"libtasn1\.so\.6", r"libnettle\.so\.8", r"libhogweed\.so\.6",
           r"libgmp\.so\.10", r"libidn2\.so\.0", r"libssl\.so\.3", r"libcrypto\.so\.3", r"libgssapi_krb5\.so\.2",
           r"libkrb5\.so\.3", r"libk5crypto\.so\.3", r"libcom_err\.so\.2", r"libkrb5support\.so\.0",
           r"libkeyutils\.so\.1", r"libavahi-client\.so\.3", r"libavahi-common\.so\.3", r"libsqlite3\.so\.0"]
_SO_BASE = re.compile("^(" + "|".join(SO_BASE) + ")$")
_PKG_BASE = re.compile("^(" + "|".join(PKG_BASE) + ")$")


def di_base(soname):
    return bool(_SO_BASE.match(soname))


# --------------------------------------------------------------------------- ELF (solo 64 bit little endian)
def elf_info(path):
    """(lista NEEDED, SONAME, RUNPATH o RPATH) di un file ELF; None se non è un ELF 64 bit con sezione dinamica."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    if data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        return None
    phoff = struct.unpack_from("<Q", data, 0x20)[0]
    phentsize, phnum = struct.unpack_from("<HH", data, 0x36)
    loads, dyn = [], None
    for i in range(phnum):
        p_type, _f, p_offset, p_vaddr, _pa, p_filesz, _m, _al = struct.unpack_from("<IIQQQQQQ", data,
                                                                                   phoff + i * phentsize)
        if p_type == 1:
            loads.append((p_vaddr, p_offset, p_filesz))
        elif p_type == 2:
            dyn = (p_offset, p_filesz)
    if dyn is None:
        return None
    needed, soname, strtab, runpath = [], None, None, None
    for j in range(0, dyn[1], 16):
        tag, val = struct.unpack_from("<qQ", data, dyn[0] + j)
        if tag == 0:
            break
        if tag == 1:
            needed.append(val)
        elif tag == 14:
            soname = val
        elif tag == 5:
            strtab = val
        elif tag in (15, 29):
            runpath = val
    off = next((v - va + o for va, o, sz in loads for v in [strtab] if va <= v < va + sz), None)
    if off is None:
        return None

    def s(n):
        return data[off + n:data.index(b"\0", off + n)].decode()

    return ([s(n) for n in needed], (s(soname) if soname is not None else None),
            (s(runpath) if runpath is not None else ""))


# --------------------------------------------------------------------------- pacchetti Ubuntu
def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw).stdout


def dipendenze_pacchetti(iniziali):
    """Chiusura delle dipendenze (Depends) dei pacchetti, fermandosi a quelli di base."""
    visti, coda, tenuti = set(), list(iniziali), []
    opzioni = ["--no-recommends", "--no-suggests", "--no-conflicts", "--no-breaks", "--no-replaces",
               "--no-enhances", "--no-pre-depends"]
    while coda:
        lotto = [p for p in dict.fromkeys(coda) if p not in visti]
        coda = []
        if not lotto:
            break
        visti.update(lotto)
        out = subprocess.run(["apt-cache", "depends"] + opzioni + lotto, capture_output=True, text=True).stdout
        corrente, in_alt, attesa_fornitore = None, False, False
        for line in out.splitlines():
            if not line.startswith(" "):
                corrente = line.strip()
                if corrente and not corrente.startswith("<"):
                    tenuti.append(corrente)
                in_alt = attesa_fornitore = False
                continue
            m = re.match(r"^ (\|| )Depends: (.+)$", line)
            if m:
                prendi = not in_alt
                in_alt = m.group(1) == "|"
                nome = m.group(2).strip()
                attesa_fornitore = False
                if not prendi:
                    continue
                if nome.startswith("<"):
                    attesa_fornitore = True  # pacchetto virtuale: si prende il primo che lo fornisce
                    continue
                nome = nome.split(":")[0]
                if not _PKG_BASE.match(nome):
                    coda.append(nome)
            elif attesa_fornitore and line.startswith("    "):
                nome = line.strip().split(":")[0]
                attesa_fornitore = False
                if not _PKG_BASE.match(nome):
                    coda.append(nome)
    return sorted(set(t.split(":")[0] for t in tenuti))


def scarica_ed_estrai(pacchetti, debs, stage):
    """apt-get download + dpkg-deb -x di ogni pacchetto in stage/<pacchetto>. Ritorna {pacchetto: versione}."""
    os.makedirs(debs, exist_ok=True)
    mancanti = [p for p in pacchetti if not glob.glob(os.path.join(debs, f"{p}_*.deb"))]
    for i in range(0, len(mancanti), 40):
        lotto = mancanti[i:i + 40]
        if subprocess.run(["apt-get", "download", "-q"] + lotto, cwd=debs, capture_output=True).returncode:
            for p in lotto:  # uno alla volta: i pacchetti solo virtuali non si scaricano
                subprocess.run(["apt-get", "download", "-q", p], cwd=debs, capture_output=True)
    versioni = {}
    os.makedirs(stage, exist_ok=True)
    for p in pacchetti:
        files = sorted(glob.glob(os.path.join(debs, f"{p}_*.deb")))
        if not files:
            continue
        dest = os.path.join(stage, p)
        if not os.path.isdir(dest):
            run(["dpkg-deb", "-x", files[-1], dest])
        versioni[p] = run(["dpkg-deb", "-f", files[-1], "Version"]).strip()
    return versioni


def indice_librerie(stage, versioni):
    """{nome file .so: (pacchetto, percorso)} di tutte le librerie estratte."""
    indice = {}
    for p in versioni:
        for root, _dirs, files in os.walk(os.path.join(stage, p)):
            if "/usr/share" in root:
                continue
            for f in files:
                if ".so" in f:
                    indice.setdefault(f, (p, os.path.join(root, f)))
    return indice


def vero_file(path, radice):
    """Segue i collegamenti dentro il pacchetto estratto (anche quelli assoluti)."""
    for _ in range(20):
        if not os.path.islink(path):
            return path
        dest = os.readlink(path)
        path = os.path.join(radice, dest.lstrip("/")) if dest.startswith("/") else \
            os.path.join(os.path.dirname(path), dest)
    return path


def librerie_sistema():
    out = subprocess.run(["/sbin/ldconfig", "-p"], capture_output=True, text=True).stdout
    trovate = {}
    for line in out.splitlines():
        m = re.match(r"^\s+(\S+) \(([^)]*)\) => (\S+)$", line)
        if m and ("x86-64" in m.group(2) or "AArch64" in m.group(2)):
            trovate.setdefault(m.group(1), m.group(3))
    return trovate


def plugin_tenuto(path):
    nome = os.path.basename(path)
    if not (nome.startswith("lib") and nome.endswith("_plugin.so")):
        return False
    nome = nome[3:-len("_plugin.so")]
    return any(fnmatch.fnmatchcase(nome, k) for k in PLUGIN)


def copia_con_dipendenze(primi, dest_lib, indice, stage, sistema, usati, base_richieste, errori):
    """Copia in dest_lib le dipendenze non di base dei file «primi» (e le loro, a cascata)."""
    coda = list(primi)
    while coda:
        f = coda.pop()
        info = elf_info(f)
        if info is None:
            continue
        for so in info[0]:
            if di_base(so):
                base_richieste.add(so)
                continue
            dst = os.path.join(dest_lib, so)
            if os.path.exists(dst):
                continue
            if so in indice:
                pkg, src = indice[so]
                src = vero_file(src, os.path.join(stage, pkg))
                usati.setdefault(pkg, set()).add(so)
            elif so in sistema:
                src = os.path.realpath(sistema[so])
                usati.setdefault("(sistema della macchina di build)", set()).add(so)
            else:
                errori.append(f"{so} (richiesta da {os.path.basename(f)})")
                continue
            shutil.copyfile(src, dst)
            os.chmod(dst, 0o755)
            coda.append(dst)


def patchelf():
    p = os.environ.get("PATCHELF") or shutil.which("patchelf")
    if not p:
        sys.exit("Manca patchelf (pip install patchelf)")
    return p


def cmd_vlc(dest, lavoro, licenze, qt_xcb):
    arch = run(["dpkg", "--print-architecture"]).strip()
    multiarch = {"amd64": "x86_64-linux-gnu", "arm64": "aarch64-linux-gnu"}[arch]
    # i .deb scaricati si tengono tra una build e l'altra (TK_DEB_CACHE), gli estratti no
    stage = os.path.join(lavoro, "estratti")
    debs = os.environ.get("TK_DEB_CACHE") or os.path.join(lavoro, "deb")
    print("   dipendenze dei pacchetti VLC…")
    pacchetti = dipendenze_pacchetti(PACCHETTI_VLC + PACCHETTI_QT_XCB)
    print(f"   {len(pacchetti)} pacchetti da scaricare (apt-get download, niente installato)")
    versioni = scarica_ed_estrai(pacchetti, debs, stage)
    for p in PACCHETTI_VLC:
        if p not in versioni:
            sys.exit(f"Pacchetto {p} non scaricato: controlla apt (sources con «deb» attivi)")
    indice = indice_librerie(stage, versioni)
    sistema = librerie_sistema()

    shutil.rmtree(dest, ignore_errors=True)
    lib, plug = os.path.join(dest, "lib"), os.path.join(dest, "plugins")
    os.makedirs(lib)
    usati, base_richieste, errori = {}, set(), []
    primi = []
    # libvlc, libvlccore e le librerie private di VLC (libvlc_pulse, libvlc_xcb_events…)
    for pkg, pattern in (("libvlc5", "libvlc.so.5"), ("libvlccore9", "libvlccore.so.9")):
        src = vero_file(os.path.join(stage, pkg, "usr", "lib", multiarch, pattern), os.path.join(stage, pkg))
        shutil.copyfile(src, os.path.join(lib, pattern))
        usati.setdefault(pkg, set()).add(pattern)
        primi.append(os.path.join(lib, pattern))
    vlc_priv = os.path.join("usr", "lib", multiarch, "vlc")
    for pkg in ("vlc-plugin-base", "vlc-plugin-video-output", "libvlccore9", "libvlc5"):
        radice = os.path.join(stage, pkg, vlc_priv)
        for f in sorted(glob.glob(os.path.join(radice, "libvlc_*.so.*"))):
            info = elf_info(vero_file(f, os.path.join(stage, pkg)))
            if info and info[1] and not os.path.exists(os.path.join(lib, info[1])):
                shutil.copyfile(vero_file(f, os.path.join(stage, pkg)), os.path.join(lib, info[1]))
                usati.setdefault(pkg, set()).add(info[1])
                primi.append(os.path.join(lib, info[1]))
        for f in sorted(glob.glob(os.path.join(radice, "plugins", "*", "*_plugin.so"))):
            if plugin_tenuto(f):
                cat = os.path.basename(os.path.dirname(f))
                os.makedirs(os.path.join(plug, cat), exist_ok=True)
                dst = os.path.join(plug, cat, os.path.basename(f))
                shutil.copyfile(f, dst)
                usati.setdefault(pkg, set()).add("plugins/" + cat + "/" + os.path.basename(f))
                primi.append(dst)
    # le librerie private di VLC sono «già nel pacchetto»: l'indice le trova in lib
    for f in os.listdir(lib):
        indice[f] = ("(vlc)", os.path.join(lib, f))
    copia_con_dipendenze(primi, lib, indice, stage, sistema, usati, base_richieste, errori)
    for f in os.listdir(lib):
        os.chmod(os.path.join(lib, f), 0o755)

    # librerie xcb per Qt (X11/XWayland)
    shutil.rmtree(qt_xcb, ignore_errors=True)
    os.makedirs(qt_xcb)
    xcb_primi = []
    for so in SO_QT_XCB:
        if so in indice and indice[so][0] != "(vlc)":
            pkg, src = indice[so]
            shutil.copyfile(vero_file(src, os.path.join(stage, pkg)), os.path.join(qt_xcb, so))
            usati.setdefault(pkg, set()).add("Qt: " + so)
            xcb_primi.append(os.path.join(qt_xcb, so))
        else:
            errori.append(f"{so} (per Qt sotto X11)")
    copia_con_dipendenze(xcb_primi, qt_xcb, {k: v for k, v in indice.items() if v[0] != "(vlc)"}, stage, sistema,
                         usati, base_richieste, errori)
    if errori:
        sys.exit("Librerie non trovate nei pacchetti né nel sistema:\n  " + "\n  ".join(sorted(set(errori))))

    # RUNPATH relativo: prima il pacchetto, mai un VLC del sistema
    pe = patchelf()
    for f in glob.glob(os.path.join(lib, "*")):
        run([pe, "--set-rpath", "$ORIGIN", f])
    for f in glob.glob(os.path.join(plug, "*", "*.so")):
        run([pe, "--set-rpath", "$ORIGIN/../../lib", f])
    for f in glob.glob(os.path.join(qt_xcb, "*")):
        run([pe, "--set-rpath", "$ORIGIN", f])

    # cache dei plugin (si rigenera dopo patchelf: contiene data e dimensione dei file)
    gen = os.path.join(stage, "libvlc-bin", vlc_priv, "vlc-cache-gen")
    if os.path.isfile(gen):
        env = dict(os.environ, LD_LIBRARY_PATH=lib)
        r = subprocess.run([gen, plug], env=env, capture_output=True, text=True)
        print("   cache plugins.dat:", "creata" if os.path.isfile(os.path.join(plug, "plugins.dat"))
              else f"NON creata ({r.stderr.strip()[:200]})")

    # licenze: copyright originale di ogni pacchetto usato + elenco
    os.makedirs(licenze, exist_ok=True)
    try:
        distro = run(["lsb_release", "-ds"]).strip()
    except (OSError, subprocess.CalledProcessError):
        distro = "Ubuntu"
    righe = ["Componenti Linux di tk-tv presi dai pacchetti Ubuntu (" + distro + ")",
             "=" * 70, "",
             "libVLC, i suoi plugin e le librerie che non ci sono su ogni Ubuntu, così come li distribuisce Ubuntu",
             "(sorgenti: https://launchpad.net/ubuntu/+source/<pacchetto sorgente> e i link nei file copyright).",
             "Ogni pacchetto resta sotto la sua licenza: testo completo in deb-<pacchetto>-copyright.txt.",
             "Le librerie sono file separati in usr/lib/tk-tv/_internal/vlc dentro l'AppImage",
             "(«tk-tv-….AppImage --appimage-extract»): si possono sostituire con versioni ricompilate.", ""]
    for pkg in sorted(usati):
        if pkg.startswith("("):
            righe.append(f"{pkg}: {', '.join(sorted(usati[pkg]))}")
            continue
        sorgente = run(["dpkg-deb", "-f", sorted(glob.glob(os.path.join(debs, f"{pkg}_*.deb")))[-1],
                        "Source"]).strip() or pkg
        cr = os.path.join(stage, pkg, "usr", "share", "doc", pkg, "copyright")
        if os.path.isfile(cr):
            shutil.copyfile(cr, os.path.join(licenze, f"deb-{pkg}-copyright.txt"))
            nota = f"deb-{pkg}-copyright.txt"
        else:
            nota = "copyright nel pacchetto sorgente"
        file_pkg = sorted(usati[pkg])
        elenco = ", ".join(file_pkg) if len(file_pkg) <= 6 else f"{len(file_pkg)} file (plugin e librerie)"
        righe.append(f"{pkg} {versioni[pkg]} (sorgente {sorgente.split()[0]}) — {nota}\n    {elenco}")
    righe += ["", "Librerie di base usate dal sistema (non incluse): " + ", ".join(sorted(base_richieste))]
    with open(os.path.join(licenze, "LINUX-PACCHETTI.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(righe) + "\n")
    with open(os.path.join(lavoro, "vlc-versione.txt"), "w", encoding="utf-8") as fh:
        fh.write(versioni["libvlc5"].split(":")[-1].split("-")[0])

    n_plug = len(glob.glob(os.path.join(plug, "*", "*.so")))
    peso = sum(os.path.getsize(os.path.join(r, f)) for r, _d, fs in os.walk(dest) for f in fs)
    print(f"   libVLC {versioni['libvlc5']}: {n_plug} plugin, {len(os.listdir(lib))} librerie, "
          f"{peso / 1048576:.0f} MB; librerie xcb per Qt: {len(os.listdir(qt_xcb))}")
    print("   librerie di base richieste al sistema:", " ".join(sorted(base_richieste)))
    return 0


def cmd_controlla(cartella):
    """Ogni dipendenza diretta di ogni file del pacchetto deve stare nel pacchetto (cercata come fa il sistema:
    RUNPATH e LD_LIBRARY_PATH=_internal impostato da PyInstaller) oppure essere una libreria di base."""
    interno = os.path.join(cartella, "_internal")
    ld_path = [interno] if os.path.isdir(interno) else []
    sistema = librerie_sistema()
    controllati, mancano, base, base_assenti = 0, {}, set(), set()
    for root, _dirs, files in os.walk(cartella):
        for f in files:
            p = os.path.join(root, f)
            if os.path.islink(p) or not os.path.isfile(p):
                continue
            info = elf_info(p)
            if info is None:
                continue
            controllati += 1
            dirs = [d.replace("$ORIGIN", root).replace("${ORIGIN}", root) for d in info[2].split(":") if d] + ld_path
            for so in info[0]:
                if di_base(so):
                    base.add(so)
                    if so not in sistema:
                        base_assenti.add(so)
                elif not any(os.path.exists(os.path.join(d, so)) for d in dirs):
                    nota = " (c'è solo nel sistema di build)" if so in sistema else ""
                    mancano.setdefault(so + nota, os.path.relpath(p, cartella))
    print(f"   controllati {controllati} file ELF; librerie di base usate: {len(base)}")
    if base_assenti:
        print("   librerie di base assenti su QUESTA macchina (su Ubuntu desktop ci sono):",
              " ".join(sorted(base_assenti)))
    if mancano:
        for so, chi in sorted(mancano.items()):
            print(f"   MANCA {so} (richiesta da {chi})")
        return 1
    print("   nessuna libreria mancante")
    return 0


def main(argv):
    os.environ["LC_ALL"] = "C"  # apt e ldd in inglese: si leggono i loro messaggi
    if len(argv) == 5 and argv[0] == "vlc":
        return cmd_vlc(*[os.path.abspath(a) for a in argv[1:]])
    if len(argv) == 2 and argv[0] == "controlla":
        return cmd_controlla(os.path.abspath(argv[1]))
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
