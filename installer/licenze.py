"""Crea la cartella «licenze» del pacchetto di tk-tv (Windows e Mac): solo libreria standard.

Uso: python -I installer/licenze.py <cartella_destinazione> --site <site-packages> [--vlc <cartella_vlc>]
                                   [--python-licenza <LICENSE.txt>] [--mac]

Copia la licenza AGPL di tk-tv (COPYING), i testi in licenze/ del repo, le licenze dai *.dist-info dei
pacchetti inclusi e il COPYING di VLC, poi scrive COMPONENTI.txt (componente, versione, licenza, sorgente).
"""
import argparse
import glob
import os
import platform
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VLC_VER = "3.0.24"
TESTI = ["COPYING-AGPL-3.0.txt", "LGPL-2.1.txt", "GPL-2.0.txt", "LGPL-3.0.txt", "GPL-3.0.txt", "MPL-2.0.txt",
         "Apache-2.0.txt", "MIT.txt", "Python-PSF.txt"]


def versione_tktv():
    with open(os.path.join(ROOT, "tktv", "__init__.py"), encoding="utf-8") as fh:
        return re.search(r'VERSION = "(.+)"', fh.read()).group(1)


def dist_info(site, nome):
    """(versione, cartella dist-info) del pacchetto installato, oppure ('', None)."""
    for d in glob.glob(os.path.join(site, "*.dist-info")):
        base = os.path.basename(d)[:-len(".dist-info")]
        pkg, _, ver = base.rpartition("-")
        if pkg.lower().replace("-", "_") == nome.lower().replace("-", "_"):
            return ver, d
    return "", None


def copia_licenze_dist(d, prefisso, dest):
    """Copia i file di licenza dichiarati nel dist-info (cartella licenses/ o COPYING/LICENSE in radice)."""
    copiati = []
    if not d:
        return copiati
    candidati = glob.glob(os.path.join(d, "licenses", "**", "*"), recursive=True) + \
        [p for p in glob.glob(os.path.join(d, "*")) if os.path.basename(p).upper().startswith(("COPYING", "LICENSE"))]
    for p in candidati:
        if not os.path.isfile(p) or "commercial" in os.path.basename(p).lower():
            continue  # la nota della licenza commerciale di Qt non riguarda questa copia (LGPL)
        nome = f"{prefisso}-{os.path.splitext(os.path.basename(p))[0]}.txt"
        shutil.copyfile(p, os.path.join(dest, nome))
        copiati.append(nome)
    return copiati


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("dest")
    ap.add_argument("--site", required=True)
    ap.add_argument("--vlc", default="")
    ap.add_argument("--python-licenza", default="")
    ap.add_argument("--mac", action="store_true")
    a = ap.parse_args(argv)

    os.makedirs(a.dest, exist_ok=True)
    shutil.copyfile(os.path.join(ROOT, "COPYING"), os.path.join(a.dest, "COPYING-AGPL-3.0.txt"))
    for t in TESTI[1:]:
        shutil.copyfile(os.path.join(ROOT, "licenze", t), os.path.join(a.dest, t))
    if a.python_licenza and os.path.isfile(a.python_licenza):
        # quello del runtime incluso: contiene anche le note di OpenSSL, libffi, bzip2… di questa build
        shutil.copyfile(a.python_licenza, os.path.join(a.dest, "Python-PSF.txt"))
    vlc_copying = os.path.join(a.vlc, "COPYING.txt") if a.vlc else ""
    if vlc_copying and os.path.isfile(vlc_copying):
        shutil.copyfile(vlc_copying, os.path.join(a.dest, "VLC-COPYING.txt"))
    else:
        # il COPYING di VLC è il testo della GPL-2.0
        shutil.copyfile(os.path.join(ROOT, "licenze", "GPL-2.0.txt"), os.path.join(a.dest, "VLC-COPYING.txt"))

    ver = versione_tktv()
    pyside, d_pyside = dist_info(a.site, "pyside6_essentials")
    shiboken, d_shiboken = dist_info(a.site, "shiboken6")
    pyvlc, d_pyvlc = dist_info(a.site, "python_vlc")
    certifi, d_certifi = dist_info(a.site, "certifi")
    extra = []
    extra += copia_licenze_dist(d_pyvlc, "python-vlc", a.dest)
    extra += copia_licenze_dist(d_certifi, "certifi", a.dest)
    extra += copia_licenze_dist(d_pyside, "PySide6", a.dest)
    extra += copia_licenze_dist(d_shiboken, "shiboken6", a.dest)

    righe = [
        f"tk-tv {ver} — componenti inclusi in questo pacchetto",
        "=" * 60,
        "",
        "Ogni componente resta sotto la sua licenza; i testi sono in questa cartella.",
        "Le librerie (DLL/dylib di Qt e di VLC) sono file separati: si possono sostituire con",
        "una versione modificata dagli stessi sorgenti, come chiedono LGPL-2.1 e LGPL-3.0.",
        "",
        f"tk-tv {ver}",
        "  Licenza: GNU AGPL-3.0-or-later (COPYING-AGPL-3.0.txt)",
        f"  Sorgente: https://github.com/tecnikgeek-repo/tk-tv-desktop/tree/v{ver}",
        "  Il nome «tk-tv» e il logo non sono coperti dalla licenza: una versione modificata",
        "  deve avere un nome diverso.",
        "",
        f"Python {platform.python_version()}",
        "  Licenza: PSF-2.0 (Python-PSF.txt)",
        "  Sorgente: https://www.python.org/downloads/source/",
        "  Include OpenSSL (Apache-2.0, Apache-2.0.txt, https://www.openssl.org/source/),",
        "  libffi (MIT, MIT.txt, https://github.com/libffi/libffi) e le altre librerie elencate",
        "  in Python-PSF.txt.",
        "",
        f"Qt for Python: PySide6 {pyside or '?'} e shiboken6 {shiboken or '?'}, con le librerie Qt 6",
        "  Licenza: LGPL-3.0 (LGPL-3.0.txt + GPL-3.0.txt); in alternativa GPL-2.0 o GPL-3.0",
        "  Sorgente: https://download.qt.io/official_releases/QtForPython/",
        "            https://code.qt.io/cgit/pyside/pyside-setup.git",
        "            https://download.qt.io/official_releases/qt/",
        "",
        f"VLC / libVLC {VLC_VER} (VideoLAN)",
        "  Licenza: LGPL-2.1-or-later per libvlc e libvlccore e la maggior parte dei plugin,",
        "           GPL-2.0-or-later per alcuni plugin (VLC-COPYING.txt, LGPL-2.1.txt, GPL-2.0.txt)",
        f"  Sorgente: https://download.videolan.org/pub/videolan/vlc/{VLC_VER}/",
        "  Incluso solo un sottoinsieme dei plugin (quelli per guardare i flussi di rete).",
        "",
        f"python-vlc {pyvlc or '?'}",
        "  Licenza: LGPL-2.1-or-later (LGPL-2.1.txt)",
        "  Sorgente: https://pypi.org/project/python-vlc/ · https://github.com/oaubert/python-vlc",
        "",
        f"certifi {certifi or '?'}",
        "  Licenza: MPL-2.0 (MPL-2.0.txt)",
        "  Sorgente: https://pypi.org/project/certifi/ · https://github.com/certifi/python-certifi",
    ]
    if a.mac:
        righe += [
            "",
            "Material Icons Round (font delle icone)",
            "  Licenza: Apache-2.0 (Apache-2.0.txt)",
            "  Sorgente: https://github.com/google/material-design-icons",
            "",
            "PyInstaller (avvio dell'app)",
            "  Licenza: GPL-2.0-or-later con eccezione per il bootloader (GPL-2.0.txt)",
            "  Sorgente: https://github.com/pyinstaller/pyinstaller",
        ]
    else:
        righe += [
            "",
            "Microsoft Visual C++ Runtime (vcruntime140.dll, msvcp140.dll…)",
            "  File di sistema ridistribuibili di Microsoft inclusi con Python e Qt (licenza Microsoft).",
        ]
    if extra:
        righe += ["", "Licenze copiate dai pacchetti: " + ", ".join(sorted(extra))]
    with open(os.path.join(a.dest, "COMPONENTI.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(righe) + "\n")
    print(f"   licenze: {len(os.listdir(a.dest))} file in {a.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
