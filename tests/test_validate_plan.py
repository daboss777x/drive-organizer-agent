import pytest
from validate_plan import validate

CFG = {"ask_threshold": 0.7,
       "categories": ["Clients", "Business Operations", "Content", "Learning", "Personal", "Finance", "Archive"]}


def cand(id, name="notes.txt", path="", **kw):
    return {"id": id, "name": name, "path": path, "md5Checksum": kw.get("md5")}


CANDS = [cand("a"), cand("b", "Untitled document"), cand("c", "Northbeam contract.pdf"),
         cand("d", "old meme.png"), cand("e", "Q3 plan (1).docx")]
SUMS = {"a": {"doc_type": "notes", "business_relevance": "low"},
        "c": {"doc_type": "contract", "business_relevance": "high"},
        "d": {"doc_type": "image", "business_relevance": "low"}}


def v(*items, groups=()):
    return validate(list(items), CANDS, SUMS, CFG, dup_groups=list(groups))


def item(id, action, conf=0.9, **kw):
    return {"id": id, "action": action, "confidence": conf, "reason": "r", **kw}


def test_valid_move_is_accepted():
    out = v(item("a", "move", target_folder="Learning/University"))
    assert [a["id"] for a in out["actions"]] == ["a"]


@pytest.mark.parametrize("bad", [
    item("a", "delete"), item("a", "trash"), item("a", "share"),
    item("NOT_A_CANDIDATE", "move", target_folder="Content"),
])
def test_unknown_actions_and_ids_are_rejected(bad):
    out = v(bad)
    assert out["actions"] == [] and len(out["rejected"]) == 1


def test_low_confidence_move_or_rename_is_acted_on_not_asked():
    """Autonomy (the owner, 2026-11-13): moves/renames are undoable, so confidence never blocks them."""
    out = v(item("a", "move", conf=0.3, target_folder="Content"),
            item("b", "rename", conf=0.2, new_name="Kickoff notes"))
    assert [a["id"] for a in out["actions"]] == ["a", "b"] and out["questions"] == []


def test_explicit_ask_becomes_a_question():
    out = v(item("a", "ask", target_folder="Content"))
    assert out["questions"][0]["id"] == "a"


def test_archiving_a_business_doc_becomes_a_question_not_an_action():
    out = v(item("c", "archive"))
    assert out["actions"] == [] and out["questions"][0]["id"] == "c"


def test_files_under_clients_or_finance_are_never_archived_without_asking():
    cands = [cand("x", "scan.png", path="Clients/Northbeam/Reports")]
    out = validate([item("x", "archive")], cands, {}, CFG)
    assert out["actions"] == [] and out["questions"][0]["id"] == "x"


def test_low_value_file_can_be_archived():
    assert [a["id"] for a in v(item("d", "archive"))["actions"]] == ["d"]


@pytest.mark.parametrize("id,new,ok", [
    ("b", "Northbeam kickoff notes", True),      # Untitled*
    ("e", "Q3 plan.docx", True),                 # * (1)
    ("a", "renamed.txt", False),                 # notes.txt is not broken
    ("b", "Copy of thing", False),               # new name itself broken
    ("b", "a/b", False),                         # path separator
    ("b", "", False),
])
def test_rename_only_fixes_broken_names(id, new, ok):
    out = v(item(id, "rename", new_name=new))
    assert bool(out["actions"]) is ok


@pytest.mark.parametrize("target,ok", [
    ("Clients/Northbeam/Contracts", True), ("Content", True),
    ("Claude Skills", True), ("Events/Tellit", True),          # new top-level folders allowed
    ("Archive", False), ("Archive/old", False), ("_DriveAgent", False), ("_DriveAgent/x", False),
    ("Clients/../_DriveAgent", False), ("Clients/./x", False), ("", False), ("/Content", False),
    ("Content/", False), ("Content//x", False),
])
def test_move_target_may_be_new_but_must_be_safe(target, ok):
    out = v(item("a", "move", target_folder=target))
    assert bool(out["actions"]) is ok


def test_dedupe_archive_requires_a_real_duplicate_group():
    good = v(item("a", "dedupe_archive", keep_id="d"), groups=[["d", "a"]])
    bad = v(item("a", "dedupe_archive", keep_id="d"), groups=[])
    assert good["actions"] and not bad["actions"]


def test_owners_explicit_archive_answer_overrides_business_default():
    assert v(item("c", "archive", source="owner"))["actions"]
    assert not v(item("c", "archive", source="agent"))["actions"]


# ---- review: edge cases ----
@pytest.mark.parametrize("conf", [None, "high", "nan"])
def test_missing_or_junk_confidence_on_an_archive_becomes_a_question(conf):
    it = {"id": "d", "action": "archive", "confidence": conf}
    assert v(it)["questions"] and not v(it)["actions"]


def test_move_target_with_a_guard_sensitive_name_is_rejected():
    out = v(item("a", "move", target_folder="Finance/Bank statements"))
    assert out["actions"] == [] and out["rejected"]


def test_agent_may_move_or_rename_a_name_flagged_file_unread():
    out = validate([item("a", "move", target_folder="Finance"), item("b", "rename", new_name="Accounts")],
                   CANDS, SUMS, CFG, unread={"a", "b"})
    assert [x["id"] for x in out["actions"]] == ["a", "b"]


@pytest.mark.parametrize("it", [item("d", "archive"), item("d", "dedupe_archive", keep_id="a"),
                                item("d", "ask")])
def test_name_flagged_files_cannot_be_archived_or_asked_about(it):
    out = validate([it], CANDS, SUMS, CFG, dup_groups=[["a", "d"]], unread={"d"})
    assert out["actions"] == [] and out["questions"] == []
    assert "not read: only move/rename allowed" in out["rejected"][0]["rejected_because"]


@pytest.mark.parametrize("it", [item("a", "move", target_folder="Personal"),
                                item("b", "rename", new_name="Passport"),
                                item("d", "archive"), item("a", "move", target_folder="Personal",
                                                           source="owner")])
def test_untouchable_files_get_no_action_at_all(it):
    out = validate([it], CANDS, SUMS, CFG, untouchable={it["id"]})
    assert out["actions"] == [] and out["questions"] == [] and out["rejected"]


def test_owner_can_move_a_flagged_file_unread():
    it = item("a", "move", target_folder="Personal", source="owner")
    assert validate([it], CANDS, SUMS, CFG, unread={"a"})["actions"]


def test_questions_are_capped_and_the_rest_deferred():
    cands = [cand(f"q{i}") for i in range(8)]
    plan = [item(f"q{i}", "ask") for i in range(8)]
    out = validate(plan, cands, {}, {**CFG, "max_questions_per_run": 5})
    assert len(out["questions"]) == 5 and len(out["deferred"]) == 3 and out["actions"] == []


def test_question_cap_defaults_to_five():
    cands = [cand(f"q{i}") for i in range(7)]
    out = validate([item(f"q{i}", "ask") for i in range(7)], cands, {}, CFG)
    assert len(out["questions"]) == 5


def test_exact_duplicates_are_archived_without_asking_even_at_low_confidence():
    out = v(item("a", "dedupe_archive", conf=0.1, keep_id="d"), groups=[["d", "a"]])
    assert [x["id"] for x in out["actions"]] == ["a"] and out["questions"] == []


def test_flagged_files_split_into_move_unread_and_untouchable():
    from validate_plan import split_flagged
    flagged = [{"id": "p", "name": "Passport scan.jpg", "path": ""},
               {"id": "t", "name": "2025 tax return.pdf", "path": ""},
               {"id": "x", "name": "Accountancy Sheet", "path": "Business"},
               {"id": "k", "name": "photo.jpg", "path": "Driving licence"}]
    state = {"screen_never": {"x": "Accountancy Sheet", "n": "never seen"}}
    unread, untouchable = split_flagged(flagged, state)
    assert unread == {"t"}
    assert untouchable == {"p", "k", "x", "n"}


def test_nothing_inside_the_agents_own_folder_may_be_moved_or_renamed():
    from validate_plan import validate
    cands = [{"id": "s", "name": "state.json", "path": "_DriveAgent"},
             {"id": "l", "name": "Copy of log", "path": "_DriveAgent/logs"}]
    plan = [{"id": "s", "action": "move", "target_folder": "Content", "confidence": 0.9, "reason": "r"},
            {"id": "l", "action": "rename", "new_name": "log", "confidence": 0.9, "reason": "r"}]
    out = validate(plan, cands, {}, {"categories": [], "ask_threshold": 0.7})
    assert out["actions"] == [] and len(out["rejected"]) == 2
