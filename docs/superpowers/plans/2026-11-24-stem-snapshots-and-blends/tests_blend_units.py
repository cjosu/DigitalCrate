# === Task 3: append to tests/test_units.py ===


def test_stem_snapshot_counts_as_a_weak_yes(tmp_path, monkeypatch):
    """📸 a snapshot teaches the stem mixer like locking a part does: a yes of weight 0.6, for the slots it names."""
    import sqlite3
    from digitalcrate import stems
    monkeypatch.setattr(stems, "DIR", tmp_path / "stems")
    monkeypatch.setattr(stems, "CACHE", tmp_path / "stems" / "cache")
    def _con():  # its own database: never the library's
        c = sqlite3.connect(tmp_path / "t.sqlite"); c.row_factory = sqlite3.Row
        return c
    monkeypatch.setattr(stems, "connect", _con)
    stems._LIB.update(n=-1, lib={})
    stems._EMB.clear()
    _fake_stem_song(tmp_path, 1, 100, 0, "major", 0)
    _fake_stem_song(tmp_path, 2, 110, 2, "major", 2)
    state = dict(bpm=100, key="C", slots=dict(other=dict(stem="other", track=1, bar0=0, n=4, off=0),
                                              bass=dict(stem="bass", track=2, bar0=0, n=4, off=0)))
    assert stems.log("snap", state, "bass") == 1      # one slot
    assert stems.log("snap", state) == 2              # every slot
    rows = stems._db().execute("SELECT kind, stem, y, w FROM stem_events ORDER BY rowid").fetchall()
    assert [(r["kind"], r["y"], r["w"]) for r in rows] == [("snap", 1, 0.6)] * 3
    assert rows[0]["stem"] == "bass"
