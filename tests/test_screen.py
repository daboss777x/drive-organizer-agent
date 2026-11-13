import pytest
from screen import word_flag


@pytest.mark.parametrize("name,path", [
    ("2025 tax return.pdf", ""), ("URA assessment.pdf", ""), ("Payslip March.pdf", ""),
    ("salary breakdown.xlsx", ""), ("Stanbic statement Jan.pdf", ""), ("IBAN details", ""),
    ("Mobile money records", ""), ("loan agreement.pdf", ""), ("seed phrase.txt", ""),
    ("Google backup codes.txt", ""), ("recovery key.png", ""), ("API keys", ""),
    ("prod.env", ""), ("server.pem", ""), ("Medical report.pdf", ""), ("prescription.jpg", ""),
    ("Health insurance card.png", ""), ("Driving licence front.jpg", ""), ("Visa application", ""),
    ("Work permit.pdf", ""), ("Birth certificate.pdf", ""), ("NIN slip.pdf", ""),
    ("SSN card.jpg", ""), ("Confidential - board.docx", ""), ("Last will.docx", ""),
    ("my PIN.txt", ""), ("credentials.csv", ""), ("NSSF statement", ""), ("crypto wallet", ""),
    ("diary 2024.docx", ""), ("Court summons.pdf", ""), ("therapy notes", ""),
    ("scan.pdf", "Personal/Medical"), ("doc.pdf", "Finance/Tax 2025"),
])
def test_sensitive_names_or_folders_are_flagged(name, path):
    assert word_flag(name, path)


@pytest.mark.parametrize("name,path", [
    ("Northbeam proposal.docx", "Clients/Northbeam"), ("Video script - AI agents", "Content"),
    ("Thumbnail ideas.png", ""), ("University syllabus.pdf", "Learning"), ("Q3 roadmap", ""),
    ("What will change in 2026", ""), ("Pinterest board ideas", ""), ("Taxonomy of agents", ""),
])
def test_ordinary_names_are_not_flagged(name, path):
    assert word_flag(name, path) is None


# ---------------- combining the layers ----------------
from screen import apply, needs_ai


def c(id, name, path=""):
    return {"id": id, "name": name, "path": path, "mimeType": "text/plain"}


TODO = [c("a", "Northbeam proposal"), c("b", "Payslip March"), c("c", "Mum's stuff")]


def ids(xs):
    return sorted(x["id"] for x in xs)


def test_only_unflagged_uncached_files_go_to_the_ai():
    assert ids(needs_ai(TODO, {})) == ["a", "c"]


def test_word_flag_wins_even_if_ai_says_safe():
    out = apply(TODO, [{"id": "b", "sensitive": False}, {"id": "a", "sensitive": False},
                       {"id": "c", "sensitive": False}], {})
    assert ids(out["read"]) == ["a", "c"] and ids(out["flagged"]) == ["b"]


def test_ai_can_add_flags():
    out = apply(TODO, [{"id": "a", "sensitive": False}, {"id": "c", "sensitive": True, "reason": "family"}], {})
    assert ids(out["read"]) == ["a"]
    assert {f["id"]: f["by"] for f in out["flagged"]} == {"b": "words", "c": "ai"}


def test_file_without_an_ai_verdict_is_flagged():
    out = apply(TODO, [{"id": "a", "sensitive": False}], {})
    assert "c" in ids(out["flagged"]) and "c" not in ids(out["read"])


def test_junk_ai_verdict_counts_as_sensitive():
    out = apply(TODO, [{"id": "a", "sensitive": "no"}, {"id": "c", "sensitive": False}], {})
    assert "a" in ids(out["flagged"])


def test_owner_cleared_file_is_read_until_renamed():
    state = {"screen_cleared": {"b": "Payslip March"}}
    ok = apply(TODO, [{"id": "a", "sensitive": False}, {"id": "c", "sensitive": False}], state)
    assert "b" in ids(ok["read"])
    renamed = [c("b", "Payslip April")]
    assert ids(apply(renamed, [], state)["flagged"]) == ["b"]


def test_never_read_files_are_neither_read_nor_asked_again():
    state = {"screen_never": {"b": True}}
    out = apply(TODO, [{"id": "a", "sensitive": False}, {"id": "c", "sensitive": False}], state)
    assert "b" not in ids(out["read"]) + ids(out["flagged"])


def test_ai_verdicts_are_cached_by_id_and_name():
    state = {}
    apply(TODO, [{"id": "a", "sensitive": False}, {"id": "c", "sensitive": True}], state)
    assert needs_ai(TODO, state) == []
    out = apply(TODO, [], state)  # second run, no AI call needed
    assert ids(out["read"]) == ["a"] and ids(out["flagged"]) == ["b", "c"]
    assert ids(needs_ai([c("a", "Northbeam proposal v2")], state)) == ["a"]


# ---- review: edge cases ----
from screen import is_unread


def test_garbled_ai_output_flags_everything():
    out = apply(TODO, {"not": "a list"}, {})
    assert out["read"] == [] and len(out["flagged"]) == 3


def test_ai_verdicts_for_unknown_ids_are_ignored():
    state = {}
    apply(TODO, [{"id": "zzz", "sensitive": False}], state)
    assert "zzz" not in state["screen"]


def test_file_in_a_sensitively_named_folder_stays_unread_when_seen_without_its_path():
    state = {}
    apply([c("m", "scan.pdf", "Personal/Medical")], [{"id": "m", "sensitive": False}], state)
    assert is_unread(state, {"id": "m", "name": "scan.pdf"}) is True


def test_ai_verdicts_from_an_older_screener_prompt_are_rechecked(monkeypatch):
    """When screener.md changes, cached AI verdicts must be re-judged. The owner's own answers stay."""
    import screen
    f = {"id": "p1", "name": "IMG_1376.HEIC", "path": "Photo Booth"}
    monkeypatch.setattr(screen, "screener_version", lambda: "v1")
    state = {}
    screen.apply([f], [{"id": "p1", "sensitive": True, "reason": "private photo"}], state)
    assert screen.needs_ai([f], state) == []          # cached under v1
    monkeypatch.setattr(screen, "screener_version", lambda: "v2")
    assert screen.needs_ai([f], state) == [f]          # prompt changed: ask again
    out = screen.apply([f], [{"id": "p1", "sensitive": False}], state)
    assert [x["id"] for x in out["read"]] == ["p1"]


@pytest.mark.parametrize("name,path,strict", [
    ("Passport scan.jpg", "", True), ("API keys", "", True), ("Medical report.pdf", "", True),
    ("notes.txt", "Driving licence", True),                    # sensitive folder in the path
    ("2025 tax return.pdf", "", False), ("Stanbic statement Jan.pdf", "", False),  # finance: move unread
    ("diary 2024.docx", "", False), ("Accountancy Sheet", "", False), ("plan.txt", "", False),
])
def test_strict_flag_only_for_identity_credentials_and_health(name, path, strict):
    from screen import strict_flag
    assert strict_flag(name, path) is strict
