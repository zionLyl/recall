"""Tests for bi-temporal memory (point-in-time queries + supersession history)."""

import tempfile
from pathlib import Path

from engram.store import Store


def _tmp_store() -> Store:
    d = tempfile.mkdtemp()
    return Store(Path(d) / "test.db")


def _set_window(s, mid, valid_from, valid_to=None, active=1):
    s.conn.execute(
        "UPDATE memories SET valid_from=?, valid_to=?, active=? WHERE id=?",
        (valid_from, valid_to, active, mid),
    )
    s.conn.commit()


def test_as_of_window():
    s = _tmp_store()
    a = s.add_memory("I live in NYC")
    b = s.add_memory("I live in Berlin")
    # A valid 100..200 (then superseded); B valid 200..now
    _set_window(s, a, 100, 200, active=0)
    _set_window(s, b, 200, None, active=1)

    # at t=150: only A was true
    at150 = [m.content for m in s.memories_as_of(150)]
    assert at150 == ["I live in NYC"]
    # at t=250: only B
    at250 = [m.content for m in s.memories_as_of(250)]
    assert at250 == ["I live in Berlin"]
    # at t=50: nothing existed yet
    assert s.memories_as_of(50) == []


def test_as_of_includes_inactive_within_window():
    s = _tmp_store()
    a = s.add_memory("temporary fact")
    _set_window(s, a, 100, 300, active=0)        # deactivated, but valid 100..300
    assert len(s.memories_as_of(200)) == 1        # still surfaced for its window
    assert s.all_memories() == []                 # but not "current" (active-only)


def test_as_of_scope_filter():
    s = _tmp_store()
    w = s.add_memory("work note", scope="work")
    h = s.add_memory("home note", scope="home")
    _set_window(s, w, 100, None)
    _set_window(s, h, 100, None)
    assert len(s.memories_as_of(150, scope="work")) == 1
    assert len(s.memories_as_of(150)) == 2


def test_soft_delete_sets_valid_to():
    s = _tmp_store()
    mid = s.add_memory("ephemeral")
    s.soft_delete(mid)
    m = s.get_memory(mid)
    assert m.active == 0
    # its validity window is now closed, so a "now+1" query excludes it
    import time
    assert all(x.id != mid for x in s.memories_as_of(time.time() + 1))
