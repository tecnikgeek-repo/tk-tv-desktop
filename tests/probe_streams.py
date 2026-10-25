"""Verifica che libVLC apra davvero i flussi della playlist (senza finestra): stato Playing + dimensione video."""
import os
import site
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
site.addsitedir(os.path.join(ROOT, ".venv", "Lib", "site-packages"))
sys.path.insert(0, ROOT)

from tktv import engine, playlist  # noqa: E402

url = os.environ["TKTV_TEST_URL"]
names = sys.argv[1:] or ["Rai 1", "Canale 5", "LA7", "TV8", "Rai 3"]
_, channels = playlist.download(url)
vlc = engine.load()
inst = vlc.Instance(["--quiet", "--no-lua", "--ignore-config", "--vout=dummy", "--aout=dummy",
                     "--network-caching=2000", "--adaptive-logic=highest"])
for name in names:
    ch = next((c for c in channels if c.name == name), None)
    if ch is None:
        print(f"{name}: non in playlist")
        continue
    mp = inst.media_player_new()
    m, _ = engine.make_media(ch, inst)  # stesse opzioni dell'app
    mp.set_media(m)
    mp.play()
    t0 = time.time()
    size = (0, 0)
    while time.time() - t0 < 20:
        st = mp.get_state()
        size = mp.video_get_size(0) or (0, 0)
        if st == vlc.State.Error or (st == vlc.State.Playing and size[0] > 0):
            break
        time.sleep(0.3)
    print(f"{name}: {mp.get_state()} video={size[0]}x{size[1]} in {time.time() - t0:.1f}s")
    mp.stop()
    mp.release()
