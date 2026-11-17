import json
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


def test_files_that_became_protected_are_forgotten_everywhere():
    """A file moved into the forbidden folder after a scan must leave no ID or name in memory."""
    P, K = "PROTECTED000000000000000000000", "KEEPME00000000000000000000000"
    s = {"screen": {P: {"name": "secret.pdf"}, K: {"name": "brief.pdf"}},
         "summaries": {P: {"summary": "x"}, K: {"summary": "y"}},
         "seen": {P: "1", K: "1"}, "placed": {P: "1"}, "placed_to": {P: "Content"},
         "screen_cleared": {P: "secret.pdf"}, "screen_never": {P: "secret.pdf"},
         "history": [{"id": P, "name": "secret.pdf"}, {"id": K, "name": "brief.pdf"}],
         "corrections": [{"id": P, "name": "secret.pdf"}],
         "feedback": [{"id": P, "name": "secret.pdf", "answer": "x"}, {"rule": "zips -> client"}],
         "open_questions": [{"id": P, "name": "secret.pdf", "question": "?"}]}
    dropped = st.prune_protected(s, allowed=lambda i: i == K)
    assert dropped == 1
    assert "secret.pdf" not in json.dumps(s) and P not in json.dumps(s)
    assert s["screen"] == {K: {"name": "brief.pdf"}} and s["history"] == [{"id": K, "name": "brief.pdf"}]
    assert s["feedback"] == [{"rule": "zips -> client"}]   # rules without a file stay


# ---- reorganise the whole Drive (the owner, 2026-11-17) ----
def test_reorganise_forgets_what_was_decided_but_keeps_what_was_learned():
    from state import reorganise
    s = {"seen": {"a": "t"}, "placed": {"b": "t"}, "scan_since": "2026-11-17T11:36:00Z",
         "placed_to": {"b": "Clients"}, "summaries": {"a": {}}, "screen": {"a": {}},
         "screen_never": {"x": 1}, "corrections": [{"id": "b"}], "history": [{"id": "a"}],
         "feedback": [{"id": "a"}], "structure": "old map"}
    reorganise(s)
    assert s["seen"] == {} and s["placed"] == {} and "scan_since" not in s
    for k in ("placed_to", "summaries", "screen", "screen_never", "corrections", "history", "feedback",
              "structure"):
        assert s[k], k


def test_the_target_structure_is_saved_in_state_and_given_back_to_every_run():
    from state import save_structure, structure_text
    s = {}
    assert structure_text(s) == ""
    save_structure(s, "Clients/<Client>/Photos\nAcme Studio/Ads\n")
    assert "Acme Studio/Ads" in structure_text(s)
    save_structure(s, "   ")            # an empty write never wipes the map
    assert "Acme Studio/Ads" in structure_text(s)
