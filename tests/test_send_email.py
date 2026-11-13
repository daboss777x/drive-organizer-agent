import pytest
from send_email import build_message, ABORT_BODY


def test_report_is_sent_when_audit_passes():
    m = build_message("me@example.com", "Drive report", "Moved 3 files", audit_ok=True)
    assert m["To"] == "me@example.com" and "Moved 3 files" in m.get_content()


def test_abort_sends_only_the_fixed_security_message():
    m = build_message("me@example.com", "Drive report", "Moved SECRETNAME.txt", audit_ok=False)
    assert "SECURITY ABORT" in m["Subject"]
    assert m.get_content().strip() == ABORT_BODY.strip()
    assert "SECRETNAME" not in m.as_string()


def test_placeholder_recipient_is_refused():
    with pytest.raises(ValueError):
        build_message("<OWNER_EMAIL>", "s", "b", audit_ok=True)
