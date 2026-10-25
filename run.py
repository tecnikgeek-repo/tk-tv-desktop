import os
import site
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# Avviato con il pythonw.exe di base (app a finestra, senza console):
# aggiunge le librerie installate nel venv del progetto.
if sys.prefix == sys.base_prefix:
    site.addsitedir(os.path.join(ROOT, ".venv", "Lib", "site-packages"))
sys.path.insert(0, ROOT)

if "--warm-vlc" in sys.argv:
    # processo di riscaldamento dei plugin VLC: niente Qt, parte ed esce in pochi secondi
    from tktv.engine import warm_cli
    sys.exit(warm_cli())

from tktv.app import main

if __name__ == "__main__":
    main()
