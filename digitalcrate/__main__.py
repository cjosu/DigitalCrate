"""Command line entry point:  python -m digitalcrate <command> ...

  scan                          catalogue your music folder (tags only, fast)
  process [filters] [options]   mine samples from matching tracks
  build                         compatibility graph, kits, key/tempo views, HTML browser
  status                        summary of progress
"""
import argparse

from . import config as C


def main():
    ap = argparse.ArgumentParser(prog="digitalcrate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc0 = sub.add_parser("scan")
    sc0.add_argument("--root", help="extra folder to catalogue, e.g. '~/Found Sounds'")

    p = sub.add_parser("process")
    p.add_argument("--artist", nargs="*", default=[], help="artist names (substring match, any)")
    p.add_argument("--match", nargs="*", default=[], help="substring(s) of file path (any)")
    p.add_argument("--genre", nargs="*", default=[], help="genre tag substrings (any)")
    p.add_argument("--all", action="store_true", help="process the whole library")
    p.add_argument("--drum-only", action="store_true",
                   help="songs that so far only went through `drums` (they have drum samples but no others)")
    p.add_argument("--limit", type=int)
    p.add_argument("--ids-file", help="a JSON list of track ids to mine (from the Processing page or research/*_batch.py)")
    p.add_argument("--build", action="store_true", help="rebuild the browser page when done")
    p.add_argument("--words", action="store_true", help="transcribe the new vocal samples' words before rebuilding")
    p.add_argument("--separate", choices=["auto", "always", "never"], default="auto",
                   help="auto: separate stems unless the track is already drumless")
    p.add_argument("--reprocess", action="store_true")
    p.add_argument("--reference", action="store_true",
                   help="also process reference-only artists (their sounds go to _Reference, used as style queries)")
    p.add_argument("--top", type=int, help="process the N best tracks according to the scout ranking")
    p.add_argument("--for", dest="rank_for", choices=["vocals", "pads", "rnb"], default="vocals",
                   help="scout ranking to use with --top: exposed singing, or pads from acoustic sources")
    p.add_argument("--vocals", choices=["demucs", "roformer", "bleedless"], default="demucs",
                   help="vocal separation engine: roformer/bleedless are cleaner but ~3x slower")

    b = sub.add_parser("build")
    b.add_argument("--kits", type=int, default=60)
    sub.add_parser("status")
    ly = sub.add_parser("lyrics", help="transcribe the words in vocal samples (Whisper), for lyric search and wordless chops")
    ly.add_argument("--limit", type=int)
    rl = sub.add_parser("reloop", help="re-cut old loops onto Beat This downbeats, in place (dry run without --fix)")
    rl.add_argument("--fix", action="store_true"); rl.add_argument("--limit", type=int)
    cr = sub.add_parser("credits", help="check unmined songs' sample credits on MusicBrainz (sample-based ones are skipped)")
    cr.add_argument("--limit", type=int)
    sy = sub.add_parser("styles", help="tag every song with Discogs styles from its audio (genre gaps, related music)")
    sy.add_argument("--limit", type=int)
    bk = sub.add_parser("backup", help="back up your ratings, favourites, sketches, labels and edits (not regenerable)")
    bk.add_argument("--install", action="store_true", help="also back up nightly (launchd)")
    bk.add_argument("--restore", metavar="ZIP", help="put a backup back")
    bk.add_argument("--to", help="folder to write to (default ~/Documents/DigitalCrate Backups)")
    sub.add_parser("policy", help="apply source policy (reference / vocals_only / source) to all tracks")
    sc = sub.add_parser("scout", help="fast whole-library pass ranking tracks for exposed, sample-worthy vocals")
    sc.add_argument("--limit", type=int)
    sc.add_argument("--redo", action="store_true")
    tr = sub.add_parser("transform", help="render processed variants (micro, pop, zauberberg, glacier, freeze, ghost)")
    tr.add_argument("--recipe", nargs="+", default=["micro", "pop"])
    tr.add_argument("--ids", nargs="*", default=[], help="sample IDs (from Browser.html)")
    tr.add_argument("--file", nargs="*", default=[], help="any audio file(s)")
    tr.add_argument("--category", help="e.g. 'Pads & Atmospheres' — best N samples of a category")
    tr.add_argument("--top", type=int, default=10)
    mg = sub.add_parser("mangle", help="adaptive, randomised manipulation (profiles each sample, varies technique)")
    mg.add_argument("--ids", nargs="*", default=[])
    mg.add_argument("--file", nargs="*", default=[])
    mg.add_argument("--category")
    mg.add_argument("--top", type=int, default=5)
    mg.add_argument("--variants", type=int, default=12)
    mg.add_argument("--seed", type=int, help="reproduce a render (seed is in its .json sidecar)")
    sv = sub.add_parser("serve", help="run the browser at http://localhost:8765 (favourites, Ableton folder)")
    sv.add_argument("--port", type=int, default=8765)
    sub.add_parser("taste", help="fit the taste model and report how well it predicts your ratings")
    dr = sub.add_parser("drums", help="mine percussion: one-shots (incl. combined strikes) and loops")
    dr.add_argument("--artist", nargs="*", default=[]); dr.add_argument("--match", nargs="*", default=[])
    dr.add_argument("--top", type=int, help="N best drum tracks (acoustic genres, drums present; capped per album)")
    dr.add_argument("--limit", type=int); dr.add_argument("--redo", action="store_true")
    ig = sub.add_parser("ingest", help="add a YouTube URL, an audio file, or a folder and mine it")
    ig.add_argument("target"); ig.add_argument("--drums", action="store_true")
    ig.add_argument("--vocals", choices=["demucs", "roformer", "bleedless"], default="roformer")
    ig.add_argument("--separate", choices=["auto", "always", "never"], default="always")
    ig.add_argument("--no-build", action="store_true")
    ex = sub.add_parser("export", help="copy samples into Ableton's User Library, organised")
    ex.add_argument("--name"); ex.add_argument("--favorites", action="store_true")
    ex.add_argument("--kit"); ex.add_argument("--ids", nargs="*", default=[])
    ex.add_argument("--rack", action="store_true", help="also build an Ableton Drum Rack (.adg) of the export")
    ex.add_argument("--key", help="conform to this key (e.g. Fm, 8A)"); ex.add_argument("--bpm", type=float)
    sub.add_parser("reclassify", help="re-apply category rules to existing samples (fast, no audio work)")
    ys = sub.add_parser("ytscout", help="search YouTube, listen to a minute of each result, score for clean singing")
    ys.add_argument("query"); ys.add_argument("--n", type=int, default=15)
    ys.add_argument("--mode", choices=["voice", "pads", "guided"], default="voice",
                    help="score for singing, for pads & textures, or for your styles (guided)")
    ys.add_argument("--style", help="guided: one Discogs style to listen for, e.g. 'Funk / Soul---Neo Soul' (default: your styles)")
    so = sub.add_parser("shootout", help="render the stretch/repitch shootout (blind test at /shootout)")
    so.add_argument("--force", action="store_true"); so.add_argument("--results", action="store_true")
    so.add_argument("--tune", action="store_true", help="round 2: vocal tuning engines")
    a = ap.parse_args()

    if a.cmd == "scan":
        from .scan import scan
        scan(a.root) if a.root else scan()
    elif a.cmd == "process":
        from .process import run
        clauses, params = [], []
        for x in a.artist:
            clauses.append("artist LIKE ?"); params.append(f"%{x}%")
        for x in a.match:
            clauses.append("path LIKE ?"); params.append(f"%{x}%")
        for x in a.genre:
            clauses.append("genre LIKE ?"); params.append(f"%{x}%")
        if a.ids_file:
            import json as _j
            ids = [int(x) for x in _j.loads(open(a.ids_file).read())]
            clauses.append(f"id IN ({','.join('?' * len(ids))})"); params += ids
        if not clauses and not a.all and not a.top and not a.drum_only:
            ap.error("give --artist/--match/--genre filters, --top N, --drum-only or --all")
        where = " OR ".join(clauses) if clauses else "1=1"
        if a.drum_only:
            where = f"({where}) AND id IN (SELECT track_id FROM samples WHERE category='Percussion')"
        order = "artist, album, path"
        if a.top:
            from .scout import RANK_SQL
            w, order = RANK_SQL[a.rank_for]
            where = f"({where}) AND scout_done=1 AND {w}"
            a.limit = a.top
        run(where, params, a.separate, a.limit, a.reprocess, vocals=a.vocals,
            include_reference=a.reference, order_by=order)
        if a.words:
            print("WORDS: transcribing new vocal samples…", flush=True)
            from .lyrics import run as words
            words()
        if a.build:
            print("BUILDING the browser page…", flush=True)
            from .build import build
            build()
            print("BUILD DONE", flush=True)
    elif a.cmd == "policy":
        from .policy import apply
        apply()
    elif a.cmd == "scout":
        from .scout import scout
        scout(limit=a.limit, redo=a.redo)
    elif a.cmd == "serve":
        from .serve import serve
        serve(a.port)
    elif a.cmd == "mangle":
        from .mangle import run as mrun
        mrun(a.ids, a.file, a.category, a.top, a.variants, a.seed)
    elif a.cmd == "transform":
        from .transform import run as trun
        trun(a.recipe, a.ids, a.file, a.category, a.top)
    elif a.cmd == "taste":
        from .taste import fit
        fit(verbose=True)
    elif a.cmd == "drums":
        from .percussion import run as drun
        cl, pr = [], []
        for x in a.artist: cl.append("artist LIKE ?"); pr.append(f"%{x}%")
        for x in a.match: cl.append("path LIKE ?"); pr.append(f"%{x}%")
        if not cl and not a.top:
            ap.error("give --artist/--match or --top N")
        drun(" OR ".join(cl) if cl else "1=1", pr, a.top, a.limit, a.redo)
    elif a.cmd == "ingest":
        from .ingest import ingest
        ingest(a.target, drums=a.drums, vocals=a.vocals, separate=a.separate, rebuild=not a.no_build)
    elif a.cmd == "export":
        from .export import export, favorites_paths, kit_paths
        from .db import connect
        paths = favorites_paths() if a.favorites else kit_paths(a.kit) if a.kit else \
            [r[0] for r in connect().execute(f"SELECT path FROM samples WHERE id IN ({','.join('?'*len(a.ids))})", a.ids)]
        print(export(paths, a.name or (a.kit if a.kit else None), rack=a.rack, key=a.key, bpm=a.bpm))
    elif a.cmd == "ytscout":
        from .ytscout import run as yrun
        yrun(a.query, a.n, a.mode, a.style)
    elif a.cmd == "shootout":
        from .shootout import render, render_tune, results
        if a.tune and not a.results:
            render_tune(a.force); print("open http://localhost:8765/shootout?round=tune")
        elif a.results:
            for r in results():
                print(f"{r['material']:8} {r['method']:10} {r['avg']:.2f}  ({r['n']} votes)")
        else:
            render(a.force); print("open http://localhost:8765/shootout")
    elif a.cmd == "reclassify":
        from .process import reclassify
        reclassify()
    elif a.cmd == "reloop":
        from .reloop import run as reloop
        reloop(a.fix, a.limit)
        print("TASK DONE", flush=True)
    elif a.cmd == "credits":
        from .mbz import run as credits
        credits(a.limit)
        print("TASK DONE", flush=True)
    elif a.cmd == "styles":
        from .styles import run as styles
        styles(a.limit)
        print("TASK DONE", flush=True)
    elif a.cmd == "lyrics":
        from .lyrics import run as words
        words(a.limit)
        print("TASK DONE", flush=True)
    elif a.cmd == "build":
        from .build import build
        build(n_kits=a.kits)
    elif a.cmd == "backup":
        from .backup import backup, install, restore
        if a.restore:
            restore(a.restore)
        else:
            backup(a.to)
            if a.install:
                install()
    elif a.cmd == "status":
        from .db import connect
        con = connect()
        for r in con.execute("SELECT status, COUNT(*) n FROM tracks GROUP BY status"):
            print(f"tracks {r['status']:8s} {r['n']}")
        for r in con.execute("SELECT category, subtype, COUNT(*) n FROM samples GROUP BY 1,2 ORDER BY 1,2"):
            print(f"  {r['category']:22s} {r['subtype']:14s} {r['n']}")


if __name__ == "__main__":
    main()
