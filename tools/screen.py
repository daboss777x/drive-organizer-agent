"""Name screen: decide, from names and folder paths only, which files must NOT be read.

Layer 1 - WORD_CATALOG (this file): a match always flags; nothing can override it except
          The owner answering "Approve" in the inbox Sheet.
Layer 2 - the `screener` subagent (names + paths only, never content). It can only ADD flags.
          A file it didn't return a verdict for is flagged (fail closed).
"""
import re

SKIP_MESSAGE = "skipped: flagged for review"


class Flagged(Exception):
    def __init__(self):
        super().__init__(SKIP_MESSAGE)  # never carries a name or an ID

# category -> patterns (case-insensitive, matched against the file name and every folder in its path)
WORD_CATALOG = {
    "identity": [
        r"passport", r"\bid\b", r"national ?id", r"\bnin\b", r"\bssn\b", r"social security",
        r"\btin\b", r"birth cert", r"marriage cert", r"death cert", r"driv(er'?s?|ing) ?licen[cs]e",
        r"\blicen[cs]e (front|back|scan)", r"\bvisa\b", r"\bpermit\b", r"residen(ce|cy) card",
        r"\bkyc\b", r"identity", r"biometric", r"fingerprint",
    ],
    "finance": [
        r"\btax(es)?\b", r"tax return", r"\bura\b", r"\bp9\b", r"\bw-?2\b", r"\b1099\b",
        r"pay ?slip", r"pay ?stub", r"salar(y|ies)", r"payroll", r"statements?\b",
        r"account (number|details|no)", r"\biban\b", r"\bswift\b", r"routing number",
        r"(credit|debit|bank) ?card", r"card details", r"mobile money", r"\bmomo\b",
        r"\bloans?\b", r"mortgage", r"\bdebts?\b", r"net ?worth", r"brokerage", r"pension",
        r"\bnssf\b", r"\bcrypto", r"wallet", r"seed ?phrase", r"mnemonic", r"\bbank",
    ],
    "credentials": [
        r"credential", r"\blogins?\b", r"password", r"passcode", r"\bpins?\b", r"\bsecrets?\b",
        r"api[ _-]?keys?", r"private ?key", r"recovery (phrase|codes?|keys?)", r"backup codes?",
        r"\b2fa\b", r"\botp\b", r"\.env$", r"\benv\b", r"\.pem$", r"\.key$", r"keystore",
        r"\bssh\b", r"1password", r"bitwarden", r"lastpass", r"\btokens?\b",
    ],
    "health": [
        r"medical", r"\bhealth", r"diagnos", r"prescription", r"lab results?", r"hospital",
        r"clinic", r"therap(y|ist)", r"psychiatr", r"insurance", r"\bhiv\b", r"vaccin",
    ],
    "legal_personal": [
        r"confidential", r"lawsuit", r"\bcourt\b", r"summons", r"police", r"criminal",
        r"background check", r"divorce", r"custody", r"last will", r"testament",
        r"power of attorney", r"\bdiary\b", r"journal entr", r"\bnudes?\b", r"intimate",
        r"disciplinary", r"termination letter", r"private", r"personal data",
    ],
}
_COMPILED = [(cat, re.compile(p, re.I)) for cat, pats in WORD_CATALOG.items() for p in pats]


def word_flag(name, path=""):
    """Return 'category: pattern' if the name or any folder in the path matches, else None."""
    parts = [name or ""] + [p for p in (path or "").split("/") if p]
    for cat, rx in _COMPILED:
        if any(rx.search(p) for p in parts):
            return f"{cat}: {rx.pattern}"
    return None


STRICT_CATEGORIES = ("identity", "credentials", "health")


def strict_flag(name, path=""):
    """True for real secrets (identity, credentials, health): never read AND never moved.
    Other word-list hits (finance, legal_personal) may still be moved unread."""
    parts = [name or ""] + [p for p in (path or "").split("/") if p]
    return any(cat in STRICT_CATEGORIES and rx.search(p) for cat, rx in _COMPILED for p in parts)


def screener_version():
    """Short hash of the screener prompt. AI verdicts made under another prompt are re-checked."""
    import hashlib
    import os
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     ".claude", "agents", "screener.md")
    try:
        with open(p, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()[:12]
    except OSError:
        return "missing"


def _cached(state, f):
    hit = state.get("screen", {}).get(f["id"])
    if not hit or hit.get("name") != f["name"] or hit.get("v") != screener_version():
        return None
    return hit


def _cleared(state, f):
    return state.get("screen_cleared", {}).get(f["id"]) == f["name"]


def needs_ai(todo, state):
    """Files the screener subagent must judge: not word-flagged, not decided already."""
    return [f for f in todo
            if not _cleared(state, f) and f["id"] not in state.get("screen_never", {})
            and not word_flag(f["name"], f.get("path")) and not _cached(state, f)]


def apply(todo, ai_results, state):
    """Split todo into files safe to read and files flagged for the owner's review.
    Updates the AI verdict cache in state. Returns {"read": [...], "flagged": [...]}."""
    ai = {r.get("id"): r for r in ai_results if isinstance(r, dict)}
    cache = state.setdefault("screen", {})
    read, flagged = [], []
    for f in todo:
        if _cleared(state, f):
            read.append(f)
            continue
        if f["id"] in state.get("screen_never", {}):
            continue
        words = word_flag(f["name"], f.get("path"))
        if words:
            flagged.append({**f, "by": "words", "reason": words})
            continue
        verdict = ai.get(f["id"])
        if verdict is not None:
            sensitive = verdict.get("sensitive") is not False  # anything but a clear False
            cache[f["id"]] = {"name": f["name"], "sensitive": sensitive, "v": screener_version(),
                              "reason": str(verdict.get("reason", ""))[:200]}
        hit = _cached(state, f)
        if hit is None:
            flagged.append({**f, "by": "ai", "reason": "not screened"})
        elif hit["sensitive"]:
            flagged.append({**f, "by": "ai", "reason": hit["reason"] or "AI judged the name sensitive"})
        else:
            read.append(f)
    return {"read": read, "flagged": flagged}


def is_unread(state, f):
    """True if this file must not be read right now (used by read_file as a last check)."""
    if _cleared(state, f):
        return False
    if f["id"] in state.get("screen_never", {}) or word_flag(f["name"], f.get("path")):
        return True
    hit = _cached(state, f)
    return hit is None or hit["sensitive"]
