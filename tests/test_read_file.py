import io
import pytest
from fakes import FakeDrive, DOC
from guard import Guard, Blocked
from google_client import GoogleClient
from read_file import extract

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture
def drive():
    d = FakeDrive()
    d.folder("F", "Vault")
    return d


@pytest.fixture
def client(drive):
    return GoogleClient(drive, Guard({"F"}))


def test_google_doc_is_exported_and_truncated(client, drive):
    drive.add("d", "Northbeam proposal", mime=DOC)
    drive.text["d"] = "x" * 50
    out = extract(client, "d", max_chars=10)
    assert out["kind"] == "text" and out["text"] == "x" * 10 and out["truncated"] is True


def test_docx_text_is_extracted(client, drive):
    import docx
    doc = docx.Document()
    doc.add_paragraph("Invoice 42 for Northbeam")
    buf = io.BytesIO()
    doc.save(buf)
    drive.add("w", "inv.docx", mime=DOCX)
    drive.download = lambda id: buf.getvalue()
    assert "Invoice 42 for Northbeam" in extract(client, "w", 1000)["text"]


@pytest.mark.parametrize("mime", ["video/mp4", "audio/mpeg", "image/png"])
def test_media_returns_metadata_only_without_downloading(client, drive, mime):
    drive.add("m", "clip", mime=mime)
    out = extract(client, "m", 1000)
    assert out["kind"] == "metadata" and "text" not in out
    assert ("download", "m") not in drive.calls


def test_unreadable_pdf_falls_back_to_metadata(client, drive):
    drive.add("p", "scan.pdf", mime="application/pdf")
    drive.text["p"] = "not really a pdf"
    assert extract(client, "p", 1000)["kind"] == "metadata"


def test_blocked_file_is_refused(client, drive):
    drive.add("s", "a.txt", parent="F")
    with pytest.raises(Blocked):
        extract(client, "s", 1000)


# ---- name screen ----
from screen import Flagged


def test_word_flagged_file_is_not_read(client, drive):
    drive.add("t", "tax return 2025.txt")
    drive.text["t"] = "TIN 123"
    with pytest.raises(Flagged):
        extract(client, "t", 1000, screen_state={})
    assert ("download", "t") not in drive.calls


def test_file_not_cleared_by_the_screen_is_not_read(client, drive):
    drive.add("n", "notes.txt")
    with pytest.raises(Flagged):
        extract(client, "n", 1000, screen_state={})


def test_file_cleared_by_the_screen_is_read(client, drive):
    drive.add("n", "notes.txt")
    drive.text["n"] = "hello"
    from screen import screener_version
    state = {"screen": {"n": {"name": "notes.txt", "sensitive": False, "reason": "",
                              "v": screener_version()}}}
    assert extract(client, "n", 1000, screen_state=state)["text"] == "hello"
