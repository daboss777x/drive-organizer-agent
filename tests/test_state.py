import pytest
from fakes import FakeDrive
from guard import Guard
from google_client import GoogleClient
import state as st


def test_summary_is_reused_only_while_modified_time_is_unchanged():
    s = {}
    f = {"id": "a", "modifiedTime": "t1"}
    assert st.needs_summary(s, f) is True
    st.put_summary(s, f, {"id": "a", "summary": "x"})
    assert st.needs_summary(s, f) is False
    assert st.needs_summary(s, {"id": "a", "modifiedTime": "t2"}) is True


def test_merge_adds_batch_summaries_for_known_candidates():
    s = {}
    candidates = [{"id": "a", "modifiedTime": "t1"}, {"id": "b", "modifiedTime": "t1"}]
    batches = [[{"id": "a", "summary": "A"}], [{"id": "b", "summary": "B"}, {"id": "zz", "summary": "?"}]]
    added = st.merge(s, candidates, batches)
    assert added == 2
    assert st.get_summary(s, "b")["summary"] == "B"
    assert st.get_summary(s, "zz") is None  # unknown ids are dropped


def test_state_round_trips_through_drive_agent_folder():
    d = FakeDrive()
    c = GoogleClient(d, Guard({"F"}))
    assert st.pull(c) == {}
    st.push(c, {"last_run": "2026-11-13T15:40:00Z"})
    st.push(c, {"last_run": "2026-11-20T15:40:00Z"})
    assert st.pull(c) == {"last_run": "2026-11-20T15:40:00Z"}
    assert len([f for f in d.files.values() if f["name"] == "state.json"]) == 1


# ---- scan bookmark: only a live, complete scan may move it ----
NOW = "2026-11-20T15:40:00Z"


def test_dry_run_never_moves_the_scan_bookmark():
    s = {"scan_since": "2026-11-01T00:00:00Z"}
    st.finish_state(s, {"truncated": False}, dry_run=True, now=NOW)
    assert s["scan_since"] == "2026-11-01T00:00:00Z"


def test_capped_live_scan_keeps_the_bookmark_so_the_backlog_is_not_skipped():
    s = {}
    st.finish_state(s, {"truncated": True}, dry_run=False, now=NOW)
    assert "scan_since" not in s


def test_complete_live_scan_moves_the_bookmark():
    s = {}
    st.finish_state(s, {"truncated": False}, dry_run=False, now=NOW)
    assert s["scan_since"] == NOW


def test_digest_gives_flagged_files_by_name_only_and_hides_untouchable_ones():
    from screen import screener_version
    v = screener_version()
    cands = [{"id": "r", "name": "brief.docx", "path": ""},
             {"id": "u", "name": "Accountancy Sheet", "path": "Business"},
             {"id": "p", "name": "Passport scan.pdf", "path": ""},
             {"id": "k", "name": "Mum's things", "path": ""}]
    state = {"summaries": {"r": {"modifiedTime": None, "summary": {"summary": "a brief"}}},
             "screen": {"r": {"name": "brief.docx", "sensitive": False, "v": v, "reason": ""},
                        "u": {"name": "Accountancy Sheet", "sensitive": True, "v": v, "reason": "money"}},
             "screen_never": {"k": "Mum's things"}}
    rows = {r["id"]: r for r in st.digest_rows(state, cands)}
    assert rows["r"]["summary"]["summary"] == "a brief" and not rows["r"].get("unread")
    assert rows["u"]["unread"] is True and rows["u"]["summary"] is None   # name only
    assert "p" not in rows   # identity word-list hit: untouchable
    assert "k" not in rows   # the owner said keep where it is
