"""
rag.py - Retrieval layer.

Upgrades:
  * Structure-aware chunking: split on document structure (headings, paragraphs)
    so a whole procedure stays in one chunk instead of being cut mid-way.
  * Hybrid retrieval: blend keyword (TF-IDF) and semantic (Gemini embeddings)
    rankings via Reciprocal Rank Fusion, so exact terms AND meaning both count.
  * Embedding model is env-configurable (default gemini-embedding-001, since
    Google retired text-embedding-004 in Jan 2026).
  * Relevance signal: as well as the fused ranking, the retriever can report the
    best RAW similarity of a query to the knowledge base (relevance()). Unlike the
    RRF score (which only measures how much the two rankers AGREE on rank), the raw
    cosine similarity actually measures whether anything relevant exists at all, so
    the app can refuse to answer (and offer the account manager) instead of padding
    a thin match with invented steps.

Model / tuning knobs (all optional, via .env):
  GEMINI_EMBED_MODEL   (default gemini-embedding-001)
  CHUNK_MAX_WORDS      (default 500)
"""

import hashlib
import os
import pickle
import re
import time

import numpy as np

from utils import parse_file

try:
    import config
    _BASE_FILE = config.BASE_CONTEXT_FILE

    def _cfg(name, default):
        return config.get_secret(name) or default
except Exception:
    _BASE_FILE = None

    def _cfg(name, default):
        return os.environ.get(name) or default


EMBED_MODEL = _cfg("GEMINI_EMBED_MODEL", "gemini-embedding-001")
MAX_CHUNK_WORDS = int(_cfg("CHUNK_MAX_WORDS", "500"))
EMBED_BATCH = int(_cfg("EMBED_BATCH", "100"))
EMBED_CACHE_PATH = _cfg("EMBED_CACHE_PATH", ".embed_cache.pkl")


def _text_key(t):
    return hashlib.sha1(t.encode("utf-8")).hexdigest()


def _load_embed_cache():
    try:
        with open(EMBED_CACHE_PATH, "rb") as f:
            return pickle.load(f)
    except Exception:
        return {}


def _save_embed_cache(cache):
    try:
        with open(EMBED_CACHE_PATH, "wb") as f:
            pickle.dump(cache, f)
    except Exception:
        pass


def _retry_seconds(msg, default=5.0):
    m = re.search(r"retry in ([0-9.]+)s", msg) or re.search(r"retryDelay['\"]?:?\s*['\"]?([0-9.]+)", msg)
    try:
        return min(35.0, float(m.group(1)) + 0.5) if m else default
    except Exception:
        return default


# --------------------------------------------------------------------------- #
# Structure-aware chunking
# --------------------------------------------------------------------------- #
def chunk_text(text: str, source: str, max_words: int = None):
    """Split text into chunks.

    Paragraphs (blank-line separated) are kept whole and packed together up to
    max_words, so a whole procedure stays in one chunk rather than being split at
    every heading. Word docs create many blank lines from empty paragraphs, so
    packing by size keeps sections together instead of shredding them.
    """
    max_words = max_words or MAX_CHUNK_WORDS
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    chunks, cur, cur_words = [], [], 0

    def flush():
        nonlocal cur, cur_words
        if cur:
            chunks.append(" ".join(cur))
            cur, cur_words = [], 0

    for b in blocks:
        w = len(b.split())
        if cur and cur_words + w > max_words:
            flush()
        cur.append(b)
        cur_words += w
    flush()
    return [{"source": source, "text": t} for t in chunks if t.strip()]


def build_chunks(kb_dir: str):
    all_chunks = []
    if not os.path.exists(kb_dir):
        return all_chunks
    for filename in sorted(os.listdir(kb_dir)):
        path = os.path.join(kb_dir, filename)
        if not os.path.isfile(path) or filename.startswith((".", "~")):
            continue  # skip hidden files and Word/Excel ~$ lock files
        if _BASE_FILE and filename == _BASE_FILE:
            continue  # always-on baseline is injected separately, not indexed
        text = parse_file(path)
        if text and text.strip():
            all_chunks.extend(chunk_text(text, source=filename))
    return all_chunks


def kb_signature(kb_dir: str):
    sig = []
    if os.path.exists(kb_dir):
        for f in sorted(os.listdir(kb_dir)):
            p = os.path.join(kb_dir, f)
            if os.path.isfile(p) and not f.startswith((".", "~")):
                st = os.stat(p)
                sig.append((f, st.st_size, int(st.st_mtime)))
    return tuple(sig)


# --------------------------------------------------------------------------- #
# Rankers (each returns a ranked list of chunk indices over the shared chunks)
# --------------------------------------------------------------------------- #
class _TfidfRanker:
    engine = "keyword"

    def __init__(self, chunks):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.chunks = chunks
        self.vec = TfidfVectorizer(stop_words="english")
        self.matrix = self.vec.fit_transform([c["text"] for c in chunks]) if chunks else None

    def ranked(self, text, n):
        from sklearn.metrics.pairwise import cosine_similarity
        if not self.chunks:
            return []
        sims = cosine_similarity(self.vec.transform([text]), self.matrix)[0]
        return [int(i) for i in np.argsort(sims)[::-1][:n] if sims[i] > 0]

    def top_similarity(self, text):
        """Best keyword (TF-IDF cosine) similarity of the query to any chunk.
        Sparse, so scores run low; only used as a fallback relevance signal when
        the semantic ranker is unavailable."""
        from sklearn.metrics.pairwise import cosine_similarity
        if not self.chunks or self.matrix is None:
            return 0.0
        sims = cosine_similarity(self.vec.transform([text]), self.matrix)[0]
        return float(sims.max()) if getattr(sims, "size", 0) else 0.0


class _EmbedRanker:
    engine = "semantic"

    def __init__(self, chunks, api_key):
        from google import genai
        self._client = genai.Client(api_key=api_key)
        self.chunks = chunks
        self.matrix = self._embed([c["text"] for c in chunks]) if chunks else None

    def _embed_call(self, group):
        group = [(t or " ")[:8000] for t in group]   # keep within the model's input-token limit
        resp = self._client.models.embed_content(model=EMBED_MODEL, contents=group)
        return [e.values for e in resp.embeddings]

    def _embed_uncached(self, texts):
        """Embed texts. Try a batch first (far fewer requests); fall back to single
        calls if the model rejects batches; back off politely on 429 rate limits
        (free tier = 100 embed requests/min)."""
        out, i, batch, waits = [], 0, EMBED_BATCH, 0
        while i < len(texts):
            group = texts[i:i + batch]
            try:
                out.extend(self._embed_call(group))
                i += len(group)
                if batch == 1:
                    time.sleep(0.7)             # single mode: stay under ~100/min
            except Exception as e:
                msg = str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    waits += 1
                    if waits > 80:
                        raise
                    time.sleep(_retry_seconds(msg))
                    continue                    # retry SAME group after backoff
                if batch > 1:
                    batch = 1                   # batching unsupported -> one at a time
                    continue
                raise
        return out

    def _embed(self, texts):
        """Embed chunk texts with a persistent on-disk cache, so each chunk is only
        ever sent to the API once (restarts don't re-hit the rate limit)."""
        cache = _load_embed_cache()
        need = [t for t in texts if _text_key(t) not in cache]
        if need:
            for t, v in zip(need, self._embed_uncached(need)):
                cache[_text_key(t)] = v
            _save_embed_cache(cache)
        arr = np.array([cache[_text_key(t)] for t in texts], dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms

    def ranked(self, text, n):
        if not self.chunks:
            return []
        q = np.array(self._embed_uncached([text])[0], dtype=np.float32)
        q = q / (np.linalg.norm(q) or 1.0)
        sims = self.matrix @ q
        return [int(i) for i in np.argsort(sims)[::-1][:n]]

    def ranked_with_sims(self, text, n):
        """Rank AND return the raw cosine sims from ONE embedding of the query, so the
        caller gets both the ranking and the relevance signal without embedding twice."""
        if not self.chunks or self.matrix is None:
            return [], None
        q = np.array(self._embed_uncached([text])[0], dtype=np.float32)
        q = q / (np.linalg.norm(q) or 1.0)
        sims = self.matrix @ q
        idxs = [int(i) for i in np.argsort(sims)[::-1][:n]]
        return idxs, sims

    def top_similarity(self, text):
        """Best semantic (meaning-based) cosine similarity of the query to any chunk.
        This is the trustworthy relevance signal: high when the KB genuinely covers
        the topic (even in different words), low when it does not."""
        if not self.chunks or self.matrix is None:
            return 0.0
        q = np.array(self._embed_uncached([text])[0], dtype=np.float32)
        q = q / (np.linalg.norm(q) or 1.0)
        return float((self.matrix @ q).max())


# --------------------------------------------------------------------------- #
# Hybrid retriever (Reciprocal Rank Fusion over the rankers)
# --------------------------------------------------------------------------- #
class HybridRetriever:
    def __init__(self, chunks, rankers, engine):
        self.chunks = chunks
        self.rankers = rankers
        self.engine = engine

    def query(self, text, k=8, pool=20, rrf_k=60):
        if not self.chunks:
            return []
        scores = {}
        for r in self.rankers:
            for rank, idx in enumerate(r.ranked(text, pool)):
                scores[idx] = scores.get(idx, 0.0) + 1.0 / (rrf_k + rank + 1)
        order = sorted(scores, key=lambda i: scores[i], reverse=True)[:k]
        return [(self.chunks[i], scores[i]) for i in order]

    def query_and_relevance(self, text, k=8, pool=20, rrf_k=60):
        """query() and relevance() together, embedding the query only ONCE (the semantic
        ranker is the slow part). Returns (results, relevance). Use this in the app to
        avoid a second embedding round-trip per question."""
        if not self.chunks:
            return [], 0.0
        rankings, relevance, have_semantic = [], 0.0, False
        for r in self.rankers:
            if getattr(r, "engine", "") == "semantic" and hasattr(r, "ranked_with_sims"):
                have_semantic = True
                idxs, sims = r.ranked_with_sims(text, pool)
                rankings.append(idxs)
                if sims is not None and getattr(sims, "size", 0):
                    relevance = max(relevance, float(sims.max()))
            else:
                rankings.append(r.ranked(text, pool))
        scores = {}
        for idxs in rankings:
            for rank, idx in enumerate(idxs):
                scores[idx] = scores.get(idx, 0.0) + 1.0 / (rrf_k + rank + 1)
        order = sorted(scores, key=lambda i: scores[i], reverse=True)[:k]
        results = [(self.chunks[i], scores[i]) for i in order]
        if not have_semantic:  # keyword-only fallback: relevance from the tfidf ranker
            kw = self.rankers[0] if self.rankers else None
            fn = getattr(kw, "top_similarity", None) if kw else None
            if fn:
                try:
                    relevance = float(fn(text))
                except Exception:
                    relevance = 0.0
        return results, relevance

    def relevance(self, text):
        """Best RAW similarity (roughly 0..1) of the query to any chunk.

        Prefers the SEMANTIC ranker (meaning-based) when it exists; only falls back
        to keyword if there is no semantic ranker. This deliberately avoids using
        keyword similarity as the confidence signal, because keyword 'false friends'
        (e.g. 'market' matching 'Market Appraisals') would otherwise inflate
        confidence and let the model answer/invent on a topic that isn't really
        covered. Returns 0.0 if it can't be computed.
        """
        if not self.chunks:
            return 0.0
        semantic = next((r for r in self.rankers if getattr(r, "engine", "") == "semantic"), None)
        target = semantic or (self.rankers[0] if self.rankers else None)
        fn = getattr(target, "top_similarity", None) if target else None
        if fn is None:
            return 0.0
        try:
            return float(fn(text))
        except Exception:
            return 0.0


def get_retriever(kb_dir, gemini_key=None, use_cache=True):
    """Build a hybrid retriever. Semantic ranker is added when a Gemini key is
    present; it degrades to keyword-only if embeddings are unavailable.
    (In-memory caching is handled by the caller via st.cache_resource.)"""
    chunks = build_chunks(kb_dir)
    rankers = [_TfidfRanker(chunks)]
    engine = "keyword"
    if gemini_key:
        try:
            rankers.append(_EmbedRanker(chunks, gemini_key))
            engine = "hybrid (keyword + semantic)"
        except Exception:
            engine = "keyword (semantic unavailable)"
    return HybridRetriever(chunks, rankers, engine), {
        "engine": engine, "chunks": len(chunks), "cached": False,
    }


def format_context(results):
    """Turn retrieved (chunk, score) results into a labelled context block."""
    blocks = []
    for chunk, _score in results:
        blocks.append(f"\n\n--- SOURCE: {chunk['source']} ---\n{chunk['text']}")
    return "".join(blocks)
