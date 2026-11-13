import pytest
from fakes import FakeDrive
from guard import Guard

FORBIDDEN = "FORBIDDEN_FOLDER"


@pytest.fixture
def drive():
    d = FakeDrive()
    d.folder(FORBIDDEN, "Vault")
    d.folder("work", "Work")
    return d


@pytest.fixture
def guard():
    return Guard(folder_ids={FORBIDDEN})


def test_normal_file_is_allowed(drive, guard):
    f = drive.add("f1", "Q3 roadmap.docx", parent="work")
    assert guard.is_blocked(f, drive.get_meta) is False


def test_direct_child_of_forbidden_folder_is_blocked(drive, guard):
    f = drive.add("f2", "notes.txt", parent=FORBIDDEN)
    assert guard.is_blocked(f, drive.get_meta) is True


def test_file_three_levels_deep_is_blocked(drive, guard):
    drive.folder("a", "a", parent=FORBIDDEN)
    drive.folder("b", "b", parent="a")
    drive.folder("c", "c", parent="b")
    f = drive.add("deep", "holiday plans.txt", parent="c")
    assert guard.is_blocked(f, drive.get_meta) is True


def test_api_error_during_ancestor_walk_blocks(drive, guard):
    drive.folder("mid", "Projects", parent="work")
    f = drive.add("f3", "plan.txt", parent="mid")
    drive.fail_ids.add("mid")
    assert guard.is_blocked(f, drive.get_meta) is True


def test_shortcut_pointing_into_forbidden_folder_is_blocked(drive, guard):
    drive.add("secret", "scan.pdf", parent=FORBIDDEN)
    sc = drive.shortcut("sc1", "handy link", target="secret", parent="work")
    assert guard.is_blocked(sc, drive.get_meta) is True


def test_shortcut_to_normal_file_is_allowed(drive, guard):
    drive.add("ok", "deck.pdf", parent="work")
    sc = drive.shortcut("sc2", "deck link", target="ok", parent="root")
    assert guard.is_blocked(sc, drive.get_meta) is False


@pytest.mark.parametrize("name", [
    "Copy of Passport scan.pdf", "National ID.jpg", "BANK statement March.pdf",
    "passwords.txt", "Private notes", "forbidden stuff (1).docx",
])
def test_sensitive_name_outside_forbidden_folder_is_blocked(drive, guard, name):
    f = drive.add("n1", name, parent="work")
    assert guard.is_blocked(f, drive.get_meta) is True


@pytest.mark.parametrize("name", ["Idea list.txt", "Video ideas", "Riverside cafe menu"])
def test_innocent_names_containing_pattern_letters_are_allowed(drive, guard, name):
    f = drive.add("n2", name, parent="work")
    assert guard.is_blocked(f, drive.get_meta) is False


def test_forbidden_folder_itself_is_blocked(drive, guard):
    assert guard.is_blocked(drive.get_meta(FORBIDDEN), drive.get_meta) is True


def test_individually_forbidden_file_is_blocked(drive):
    g = Guard(folder_ids={FORBIDDEN}, file_ids={"lone"})
    f = drive.add("lone", "contract.pdf", parent="work")
    assert g.is_blocked(f, drive.get_meta) is True


def test_file_with_no_parents_is_blocked(drive, guard):
    f = drive.add("orph", "orphan.txt")
    del f["parents"]
    assert guard.is_blocked(f, drive.get_meta) is True


def test_file_inside_sensitively_named_folder_is_blocked(drive, guard):
    drive.folder("pv", "Private", parent="work")
    f = drive.add("f9", "notes.txt", parent="pv")
    assert guard.is_blocked(f, drive.get_meta) is True


def test_parent_cycle_is_blocked(drive, guard):
    drive.folder("x", "x", parent="y")
    drive.folder("y", "y", parent="x")
    f = drive.add("f10", "loop.txt", parent="x")
    assert guard.is_blocked(f, drive.get_meta) is True


def test_ancestor_lookups_are_cached_across_files(drive, guard):
    drive.folder("p1", "p1", parent="work")
    drive.folder("p2", "p2", parent="p1")
    a = drive.add("a1", "a.txt", parent="p2")
    b = drive.add("b1", "b.txt", parent="p2")
    guard.is_blocked(a, drive.get_meta)
    before = len(drive.calls)
    guard.is_blocked(b, drive.get_meta)
    assert len(drive.calls) == before


def test_assert_allowed_raises_for_blocked_id(drive, guard):
    from guard import Blocked
    drive.add("s1", "x.txt", parent=FORBIDDEN)
    with pytest.raises(Blocked):
        guard.assert_allowed("s1", drive.get_meta)


def test_assert_allowed_returns_metadata_for_allowed_id(drive, guard):
    drive.add("ok1", "x.txt", parent="work")
    assert guard.assert_allowed("ok1", drive.get_meta)["id"] == "ok1"


def test_assert_allowed_blocks_when_metadata_fetch_fails(drive, guard):
    from guard import Blocked
    with pytest.raises(Blocked):
        guard.assert_allowed("missing", drive.get_meta)


def test_unconfigured_default_guard_blocks_everything(drive, monkeypatch):
    import guard as g
    monkeypatch.setattr(g, "FORBIDDEN_FOLDER_IDS", {g.PLACEHOLDER})
    f = drive.add("f1", "Q3 roadmap.docx", parent="work")
    assert g.default_guard().is_blocked(f, drive.get_meta) is True


def test_configured_default_guard_uses_hardcoded_ids(drive, monkeypatch):
    import guard as g
    monkeypatch.setattr(g, "FORBIDDEN_FOLDER_IDS", {FORBIDDEN})
    allowed = drive.add("f1", "Q3 roadmap.docx", parent="work")
    hidden = drive.add("f2", "notes.txt", parent=FORBIDDEN)
    dg = g.default_guard()
    assert dg.is_blocked(allowed, drive.get_meta) is False
    assert dg.is_blocked(hidden, drive.get_meta) is True


# ---- review: edge cases ----
def test_innocently_renamed_file_inside_forbidden_folder_is_blocked(drive, guard):
    f = drive.add("ren", "Shopping list.txt", parent=FORBIDDEN)
    assert guard.is_blocked(f, drive.get_meta) is True


def test_shortcut_missing_target_details_is_blocked(drive, guard):
    sc = drive.add("sc3", "link", parent="work", mime="application/vnd.google-apps.shortcut")
    assert guard.is_blocked(sc, drive.get_meta) is True


def test_shortcut_whose_target_cannot_be_fetched_is_blocked(drive, guard):
    sc = drive.shortcut("sc4", "link", target="gone", parent="work")
    assert guard.is_blocked(sc, drive.get_meta) is True


# ---- config sanity: checks the real, hand-edited values in guard.py ----
def test_placeholder_marker_is_untouched():
    import guard as g
    assert g.PLACEHOLDER == "<FORBIDDEN_FOLDER_ID>", (
        "Line 7 of tools/guard.py must stay PLACEHOLDER = \"<FORBIDDEN_FOLDER_ID>\". "
        "Put your folder ID only in FORBIDDEN_FOLDER_IDS on line 8.")
