"""Keep heavy jobs from filling memory: each model-loading job loads several GB (CLAP, Demucs, Whisper), and on a
laptop that's already running Live and a browser a few of them at once push macOS into heavy swapping.

    wait(what)    before loading models: wait while memory is low (up to 10 minutes, then go ahead anyway)
    breathe()     between items of a long library pass: wait while memory is low, and on 16 GB Macs or smaller also
                  while a job you started (mining, ingest, scout) is running, so the two don't compete
"""
import fcntl
import re
import subprocess
import time

LOW = 15     # % of memory free (macOS memory_pressure) below which a heavy job waits
OK = 25      # ... and starts again once it's back above this
SMALL_MAC = 16 * 2 ** 30


def free_pct():
    try:
        out = subprocess.run(["memory_pressure", "-Q"], capture_output=True, text=True, timeout=10).stdout
        m = re.search(r"free percentage:\s*(\d+)", out)
        return int(m.group(1)) if m else 100
    except Exception:
        return 100


def ram():
    try:
        return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout)
    except Exception:
        return 0


def wait(what="starting", limit=600):
    if free_pct() >= LOW:
        return
    print(f"memory is low ({free_pct()}% free): waiting before {what}…", flush=True)
    t = time.time()
    while free_pct() < OK and time.time() - t < limit:
        time.sleep(15)
    print(f"going ahead ({free_pct()}% free, waited {time.time() - t:.0f} s)", flush=True)


def _job_running():
    """Is a job you started (it holds the jobs slot) running right now?"""
    from . import config as C
    f = C.DATA_DIR / "slot-jobs.lock"
    if not f.exists():
        return False
    with open(f, "a+") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_SH | fcntl.LOCK_NB)
            fcntl.flock(fh, fcntl.LOCK_UN)
            return False
        except BlockingIOError:
            return True


def breathe():
    import os
    if os.environ.get("DIGITALCRATE_NO_SLOT"):
        return
    small = 0 < ram() <= SMALL_MAC
    said = False
    t = time.time()
    while (small and _job_running()) or free_pct() < LOW:
        if not said:
            why = "a job you started is running" if small and _job_running() else f"memory is low ({free_pct()}% free)"
            print(f"paused: {why}; carrying on when it's done…", flush=True)
            said = True
        time.sleep(20)
        if time.time() - t > 3 * 3600:  # never stall a pass forever
            break
    if said:
        print(f"resumed after {time.time() - t:.0f} s", flush=True)
