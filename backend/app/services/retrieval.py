"""Lightweight BM25 keyword retrieval (no external services).

Used to shortlist candidates (documents, past meetings, past decisions) before the AI
reranks them. This keeps prompts small and means linking still works when AI is down.
"""
import math
import re
from collections import Counter
from dataclasses import dataclass, field

STOPWORDS = set(
    """a an the and or but if then else of to in on at for from by with without about as is are was were be been
    being it its this that these those we our you your they their he she him her i me my not no yes do does did done
    will would should could can may might must shall have has had having so than too very just also into over under
    up down out off again further once here there when where why how all any both each few more most other some such
    only own same s t don now let lets get got go going team meeting discuss discussed need needs please update next
    week today tomorrow per via etc one two new""".split()
)


def _stem(word: str) -> str:
    """Tiny suffix stripper so 'hosted', 'hosting' and 'hosts' all match 'host'."""
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9\-\+\.]*[a-z0-9]|[a-z0-9]", (text or "").lower())
    return [_stem(w) for w in words if w not in STOPWORDS and len(w) > 1]


@dataclass
class Candidate:
    kind: str  # doc | meeting | decision
    id: int
    title: str
    text: str
    meta: dict = field(default_factory=dict)
    score: float = 0.0
    matched_terms: list[str] = field(default_factory=list)


def bm25_rank(query: str, candidates: list[Candidate], top_k: int = 8, k1: float = 1.4, b: float = 0.75) -> list[Candidate]:
    q_terms = set(tokenize(query))
    if not q_terms or not candidates:
        return []
    docs = [tokenize(c.title + " " + c.title + " " + c.text) for c in candidates]  # title weighted x2
    avgdl = sum(len(d) for d in docs) / max(len(docs), 1)
    df = Counter()
    for d in docs:
        df.update(set(d))
    n = len(docs)

    ranked = []
    for cand, tokens in zip(candidates, docs):
        tf = Counter(tokens)
        score, matched = 0.0, []
        for term in q_terms:
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            freq = tf[term]
            score += idf * freq * (k1 + 1) / (freq + k1 * (1 - b + b * len(tokens) / max(avgdl, 1)))
            matched.append(term)
        if score > 0:
            cand.score = round(score, 3)
            cand.matched_terms = sorted(matched, key=lambda t: -tf[t])[:6]
            ranked.append(cand)
    ranked.sort(key=lambda c: -c.score)
    return ranked[:top_k]
