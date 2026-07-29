"""
eval.py - Tiny retrieval evaluation harness.

Measures whether the retriever pulls the RIGHT source document for a set of
known questions. Seed the eval set from your real questions (the admin
Knowledge-gaps / Log tabs are a good source).

Usage:
    python eval.py            # uses eval_set.json in this folder

eval_set.json format:
    [
      {"question": "how do I fetch enquiries?", "expect_source": "amc enquiry base.docx"},
      ...
    ]

Reports retrieval hit-rate: for each question, did the expected source appear
in the top-k retrieved passages?
"""

import json
import os
import sys

import rag

EVAL_FILE = os.path.join(os.path.dirname(__file__), "eval_set.json")
KB_DIR = os.environ.get("KB_DIR", "knowledge_base")


def run(k=8):
    if not os.path.exists(EVAL_FILE):
        print(f"No eval set found at {EVAL_FILE}. Create it (see the docstring).")
        return 1
    cases = json.load(open(EVAL_FILE, encoding="utf-8"))
    gemini_key = os.environ.get("GEMINI_API_KEY")
    retriever, info = rag.get_retriever(KB_DIR, gemini_key=gemini_key)
    print(f"Engine: {info['engine']} | chunks indexed: {info['chunks']}\n")

    hits = 0
    for case in cases:
        q = case["question"]
        expect = case["expect_source"].lower()
        results = retriever.query(q, k=k)
        sources = [c["source"].lower() for c, _ in results]
        hit = any(expect in s or s in expect for s in sources)
        hits += 1 if hit else 0
        mark = "PASS" if hit else "MISS"
        print(f"[{mark}] {q[:55]:55}  -> top sources: {sources[:3]}")

    total = len(cases)
    rate = (hits / total * 100) if total else 0
    print(f"\nRetrieval hit-rate: {hits}/{total} ({rate:.0f}%)")
    return 0 if hits == total else 2


if __name__ == "__main__":
    sys.exit(run())
