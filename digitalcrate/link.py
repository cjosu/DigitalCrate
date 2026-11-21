"""Ableton Link bridge: the server joins the Link session (enable Link in Live's top bar) and the browser asks it for
tempo + beat position, so previews and the sketchpad start on Live's bar lines at Live's tempo."""
import asyncio
import threading
import time

_state = dict(link=None, loop=None, err=None)


def _run():
    try:
        import aalink
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        link = aalink.Link(120, loop)
        link.enabled = True
        link.quantum = 4
        link.start_stop_sync_enabled = True
        _state.update(link=link, loop=loop)
        loop.run_forever()
    except Exception as e:  # aalink missing or no network permission
        _state["err"] = str(e)


def start():
    if _state["link"] is None and not _state.get("thread"):
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        _state["thread"] = t
        for _ in range(50):
            if _state["link"] is not None or _state["err"]:
                break
            time.sleep(0.02)


def status():
    start()
    link = _state["link"]
    if link is None:
        return dict(ok=False, error=_state["err"] or "starting")
    return dict(ok=True, peers=link.num_peers, tempo=round(link.tempo, 3), beat=link.beat, phase=link.phase,
                quantum=link.quantum, playing=getattr(link, "playing", None))


def set_tempo(bpm):
    start()
    link = _state["link"]
    if link is not None:
        _state["loop"].call_soon_threadsafe(lambda: setattr(link, "tempo", float(bpm)))
