from dedupe import groups

DOC = "application/vnd.google-apps.document"


def f(id, t, md5=None, name="x.pdf", mime="application/pdf"):
    return {"id": id, "modifiedTime": t, "md5Checksum": md5, "name": name, "mimeType": mime}


def test_same_md5_is_grouped_newest_first():
    out = groups([f("old", "2026-01-01", "m"), f("new", "2026-03-01", "m"), f("mid", "2026-02-01", "m")],
                 text_of=lambda i: "")
    assert out == [["new", "mid", "old"]]


def test_different_md5_is_not_grouped():
    assert groups([f("a", "1", "m1"), f("b", "2", "m2")], text_of=lambda i: "") == []


def test_google_docs_with_same_name_and_identical_text_are_grouped():
    files = [f("d1", "2026-01-01", name="Brief", mime=DOC), f("d2", "2026-02-01", name="Copy of Brief", mime=DOC)]
    assert groups(files, text_of=lambda i: "same text") == [["d2", "d1"]]


def test_google_docs_with_same_name_but_different_text_are_not_grouped():
    files = [f("d1", "1", name="Brief", mime=DOC), f("d2", "2", name="Brief (1)", mime=DOC)]
    assert groups(files, text_of=lambda i: i) == []


def test_docs_with_unique_names_are_never_exported():
    calls = []
    files = [f("d1", "1", name="Alpha", mime=DOC), f("d2", "2", name="Beta", mime=DOC)]
    groups(files, text_of=lambda i: calls.append(i) or "")
    assert calls == []


def test_files_that_may_not_be_read_are_never_exported():
    """Flagged / unread files (name screen) must not be read, not even to hash them."""
    calls = []
    files = [f("ok", "1", name="Brief", mime=DOC), f("flagged", "2", name="Copy of Brief", mime=DOC)]
    out = groups(files, text_of=lambda i: calls.append(i) or "same",
                 may_read=lambda x: x["id"] != "flagged")
    assert "flagged" not in calls
    assert out == []


def test_only_exportable_types_are_compared_and_one_failed_export_does_not_crash():
    FORM = "application/vnd.google-apps.form"
    calls = []
    def text_of(i):
        calls.append(i)
        if i == "broken":
            raise RuntimeError("export failed")
        return "same"
    files = [f("form1", "1", name="Signup", mime=FORM), f("form2", "2", name="Copy of Signup", mime=FORM),
             f("broken", "3", name="Plan", mime=DOC), f("d1", "4", name="Plan (1)", mime=DOC),
             f("d2", "5", name="Copy of Plan", mime=DOC)]
    out = groups(files, text_of=text_of)
    assert "form1" not in calls and "form2" not in calls
    assert out == [["d2", "d1"]]
