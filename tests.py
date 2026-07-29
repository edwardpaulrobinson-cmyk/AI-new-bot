"""
tests.py - Minimal smoke tests. Run offline, no API keys needed:

    python tests.py

Catches the kind of silent breakage that has bitten this app before
(model renames, retrieval regressions, logging failures). Exits non-zero on
any failure so it can gate a deploy.
"""

import os
import sys
import tempfile

FAILURES = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILURES.append(name)


def test_chunking_keeps_procedures_whole():
    import rag
    text = ("How to Fetch Enquiries\n\n"
            "Click Fetch Enquiries. Use the Source dropdown to pick the portal. Then Submit.\n\n"
            "Onboarding a landlord\n\n"
            "Collect ID and bank details, then Add Landlord.")
    chunks = rag.chunk_text(text, "doc")
    fetch = [c for c in chunks if "Fetch Enquiries" in c["text"]]
    check("chunking: fetch procedure is a single chunk", len(fetch) == 1)
    check("chunking: steps stay together",
          fetch and "Source dropdown" in fetch[0]["text"] and "Submit" in fetch[0]["text"])


def test_hybrid_fusion():
    import rag
    chunks = [{"source": "d", "text": t} for t in ["c0", "c1", "c2", "c3"]]

    class A:
        engine = "keyword"
        def ranked(self, t, n): return [0, 1][:n]

    class B:
        engine = "semantic"
        def ranked(self, t, n): return [1, 2][:n]

    hy = rag.HybridRetriever(chunks, [A(), B()], "hybrid")
    order = [chunks.index(c) for c, _ in hy.query("x", k=3)]
    check("hybrid: RRF lifts the item both rankers agree on", order[0] == 1)


def test_embedding_model_current():
    import rag
    check("embeddings: uses gemini-embedding-001 (not the retired 004)",
          rag.EMBED_MODEL == "gemini-embedding-001")


def test_logging_roundtrip():
    d = tempfile.mkdtemp()
    os.environ["LOG_DIR"] = d
    import importlib
    import interaction_log
    importlib.reload(interaction_log)
    interaction_log.log_event(status="answered", question="q1", answer="a1", provider="Gemini")
    interaction_log.log_event(status="sorted", question="q1", answer="a1", provider="Gemini")
    rows = interaction_log.read_log()
    check("logging: both events written and read back", len(rows) == 2)
    check("logging: provider recorded", rows[0].get("provider") == "Gemini")


def test_media_classify():
    import media
    check("media: png -> image", media.classify("shot.png") == "image")
    check("media: xlsx -> data", media.classify("book.xlsx") == "data")
    check("media: m4a -> audio", media.classify("note.m4a") == "audio")


def test_email_disabled_is_graceful():
    import importlib
    import config
    importlib.reload(config)
    import email_escalation
    importlib.reload(email_escalation)
    ok, _ = email_escalation.send_escalation("s", "b", attachments=[])
    check("email: disabled path returns False, no crash", ok is False)


if __name__ == "__main__":
    for fn in [
        test_chunking_keeps_procedures_whole,
        test_hybrid_fusion,
        test_embedding_model_current,
        test_logging_roundtrip,
        test_media_classify,
        test_email_disabled_is_graceful,
    ]:
        try:
            fn()
        except Exception as e:
            check(f"{fn.__name__} raised {type(e).__name__}: {e}", False)
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {FAILURES}")
        sys.exit(1)
    print("All tests passed.")
