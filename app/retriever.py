"""
Upgraded standard-library TF-IDF + cosine / RRF policy clause retriever (Stage P5/P9).

Stage P9 additions:
- Unigram + adjacent-bigram tokenisation for better phrase matching
  (e.g. "qualifying examination", "family income").
- Reciprocal Rank Fusion (RRF) merge of unigram-only and bigram-enhanced runs.
- Synonym expansion audit fix: removed the "80" token from the
  "percentage" synonym group — numeric threshold values must not be injected
  into retrieval queries because they bias scores toward evidence excerpts that
  contain the number regardless of context.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.schemas import (
    FICTIONAL_DEMO_WARNING,
    RETRIEVAL_METHOD_DISCLAIMER,
    AskResponse,
    EvidenceReference,
    RetrievalStatus,
    RetrievedPassage,
    SchemeRecord,
)

_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
        "for", "from", "how", "i", "if", "in", "is", "it", "my", "of", "on",
        "or", "should", "that", "the", "their", "this", "to", "was", "what",
        "when", "where", "which", "who", "will", "with", "would",
    }
)

# Domain synonym expansion for colloquial scholarship queries.
# AUDIT FIX (P9): "80" removed from the "percentage" synonym group.
# Numeric thresholds must not be injected into retrieval queries because
# they would inflate cosine scores for any excerpt containing that number
# regardless of context.
_DOMAIN_SYNONYMS: dict[str, tuple[str, ...]] = {
    "salary": ("income", "annum"),
    "earning": ("income", "annum"),
    "earnings": ("income", "annum"),
    "parents": ("family", "parental"),
    "father": ("family", "income"),
    "mother": ("family", "income"),
    "percentage": ("marks", "qualifying"),          # "80" removed — see audit note
    "score": ("marks", "qualifying"),
    "scored": ("marks", "qualifying"),
    "12th": ("qualifying", "examination"),
    "board": ("qualifying", "examination"),
    "college": ("enrolled", "institution", "degree", "ugc"),
    "university": ("enrolled", "institution", "degree", "ugc"),
    "regular": ("full", "time", "enrolled"),
    "concurrent": ("other", "central", "scholarship", "receipt"),
    "another": ("other", "central", "scholarship"),
    "double": ("other", "central", "scholarship"),
}

DEFAULT_SIMILARITY_THRESHOLD = 0.16
_RRF_K = 60  # standard RRF constant; rank contribution = 1 / (k + rank)


def tokenize_policy_text(
    text: str,
    *,
    expand_synonyms: bool = False,
    include_bigrams: bool = False,
) -> list[str]:
    """
    Tokenize policy or query text into normalized alphanumeric terms.

    Preserves numbers (e.g., 450000) and domain terms while removing filler words.
    Optionally appends adjacent bigrams for phrase-level matching.
    """
    cleaned = text.lower().replace("\u20b9", " rs ").replace(",", "").replace("%", " percent ")
    raw_tokens = re.findall(r"[a-z0-9]+", cleaned)
    filtered = [tok for tok in raw_tokens if tok not in _STOPWORDS and len(tok) > 1]

    if expand_synonyms:
        expanded: list[str] = []
        for tok in filtered:
            expanded.append(tok)
            if tok in _DOMAIN_SYNONYMS:
                expanded.extend(_DOMAIN_SYNONYMS[tok])
        filtered = expanded

    if include_bigrams and len(filtered) >= 2:
        bigrams = [f"{filtered[i]}_{filtered[i+1]}" for i in range(len(filtered) - 1)]
        filtered = filtered + bigrams

    return filtered


def evaluate_retrieval_benchmark(
    retriever: "PolicyClauseRetriever",
    eval_file_path: str | Path,
) -> dict[str, Any]:
    """
    Run the labelled synthetic evaluation benchmark (`data/eval_queries.json`) and
    compute Top-1 accuracy, Top-3 recall, Mean Reciprocal Rank, and refusal accuracy.

    Reported metrics reflect a small synthetic smoke benchmark, not independent
    validation of real retrieval accuracy.
    """
    path = Path(eval_file_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    queries = raw.get("queries", [])

    supported_total = 0
    top1_hits = 0
    top3_hits = 0
    reciprocal_ranks: list[float] = []

    refusal_total = 0
    refusal_hits = 0

    for item in queries:
        res = retriever.answer_query(
            item["query"],
            scheme_id=item.get("scheme_id"),
            include_fictional_demo=bool(item.get("include_fictional_demo", False)),
            top_k=3,
        )
        expected_status = RetrievalStatus(item["expected_status"])
        expected_ev_id = item.get("expected_evidence_id")

        if expected_status == RetrievalStatus.SUPPORTED_MATCH:
            supported_total += 1
            returned_ids = [p.evidence_id for p in res.passages]
            if returned_ids and returned_ids[0] == expected_ev_id:
                top1_hits += 1
            if expected_ev_id in returned_ids:
                top3_hits += 1
                rank = returned_ids.index(expected_ev_id) + 1
                reciprocal_ranks.append(1.0 / rank)
            else:
                reciprocal_ranks.append(0.0)
        else:
            refusal_total += 1
            if res.status == expected_status and len(res.passages) == 0:
                refusal_hits += 1

    return {
        "total_queries": len(queries),
        "supported_queries": supported_total,
        "refusal_queries": refusal_total,
        "top1_accuracy": round(top1_hits / supported_total, 4) if supported_total else 0.0,
        "top3_recall": round(top3_hits / supported_total, 4) if supported_total else 0.0,
        "mean_reciprocal_rank": (
            round(sum(reciprocal_ranks) / supported_total, 4) if supported_total else 0.0
        ),
        "refusal_accuracy": round(refusal_hits / refusal_total, 4) if refusal_total else 0.0,
        "note": (
            "Small synthetic smoke benchmark (10 queries). Metrics reflect in-distribution "
            "performance on queries designed alongside the evidence corpus. They are not "
            "independent validation of retrieval accuracy on unseen policy questions."
        ),
    }


def evaluate_retrieval_ablation(
    retriever: "PolicyClauseRetriever",
    eval_file_path: str | Path,
) -> dict[str, Any]:
    """
    Compare unigram-only vs bigram-enhanced vs RRF-merged retrieval on the eval corpus.

    Returns a side-by-side comparison dict for reporting in MODEL_CARD.md.
    """
    path = Path(eval_file_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    queries = [
        q for q in raw.get("queries", [])
        if q.get("expected_status") == "SUPPORTED_MATCH"
    ]

    results: dict[str, dict[str, Any]] = {"unigram": {}, "bigram": {}, "rrf": {}}
    for mode in ("unigram", "bigram", "rrf"):
        top1 = top3 = mrr_sum = 0
        for item in queries:
            res = retriever.answer_query(
                item["query"],
                scheme_id=item.get("scheme_id"),
                include_fictional_demo=bool(item.get("include_fictional_demo", False)),
                top_k=3,
                _fusion_mode=mode,
            )
            ids = [p.evidence_id for p in res.passages]
            exp = item.get("expected_evidence_id")
            if ids and ids[0] == exp:
                top1 += 1
            if exp in ids:
                top3 += 1
                mrr_sum += 1.0 / (ids.index(exp) + 1)
        n = len(queries)
        results[mode] = {
            "top1_accuracy": round(top1 / n, 4) if n else 0.0,
            "top3_recall": round(top3 / n, 4) if n else 0.0,
            "mrr": round(mrr_sum / n, 4) if n else 0.0,
        }

    return {"queries_evaluated": len(queries), "modes": results}


class PolicyClauseRetriever:
    """
    Upgraded standard-library TF-IDF + cosine similarity retriever with RRF fusion.

    Guarantees:
    - Real policy evidence and fictional demo evidence are never mixed in the same
      query execution.
    - Unverified or empty real scheme evidence explicitly returns
      INSUFFICIENT_VERIFIED_EVIDENCE.
    - Queries with similarity below threshold return NO_RELEVANT_MATCH refusal.
    - Retrieval never computes or implies an applicant eligibility verdict.

    Stage P9 upgrade: bigram-enhanced queries and Reciprocal Rank Fusion (RRF)
    merging of unigram-only and bigram-enhanced ranked lists.
    """

    def __init__(
        self,
        schemes: list[SchemeRecord],
        *,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> None:
        self._schemes_by_id: dict[str, SchemeRecord] = {s.id: s for s in schemes}
        self._threshold = similarity_threshold

    def _score_corpus(
        self,
        corpus: list[tuple[SchemeRecord, EvidenceReference, list[str]]],
        query_tokens: list[str],
    ) -> list[tuple[str, float]]:
        """
        Compute cosine-similarity scores for each corpus document against the
        query token list. Returns [(evidence_id, score)] sorted descending.
        """
        num_docs = len(corpus)
        doc_freq: Counter[str] = Counter()
        for _, _, doc_tokens in corpus:
            for tok in set(doc_tokens):
                doc_freq[tok] += 1

        def _idf(term: str) -> float:
            return math.log((1.0 + num_docs) / (1.0 + doc_freq.get(term, 0))) + 1.0

        q_counts = Counter(tok for tok in query_tokens if tok in doc_freq)
        if not q_counts:
            return []

        q_weights = {t: (1.0 + math.log(f)) * _idf(t) for t, f in q_counts.items()}
        q_norm = math.sqrt(sum(w * w for w in q_weights.values()))
        if q_norm == 0.0:
            return []

        scored: list[tuple[str, float]] = []
        for scheme, ev, doc_tokens in corpus:
            d_counts = Counter(doc_tokens)
            d_weights = {t: (1.0 + math.log(f)) * _idf(t) for t, f in d_counts.items()}
            d_norm = math.sqrt(sum(w * w for w in d_weights.values()))
            if d_norm == 0.0:
                continue
            dot = sum(q_weights.get(t, 0.0) * d_weights.get(t, 0.0) for t in q_weights)
            cosine = dot / (q_norm * d_norm)
            if cosine >= self._threshold:
                scored.append((ev.id, cosine))

        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored

    def _rrf_merge(
        self,
        ranked_a: list[tuple[str, float]],
        ranked_b: list[tuple[str, float]],
    ) -> list[tuple[str, float]]:
        """
        Reciprocal Rank Fusion of two ranked lists.

        Score for each evidence_id = sum(1/(k + rank)) across both lists.
        """
        rrf_scores: dict[str, float] = {}
        for rank, (ev_id, _) in enumerate(ranked_a, start=1):
            rrf_scores[ev_id] = rrf_scores.get(ev_id, 0.0) + 1.0 / (_RRF_K + rank)
        for rank, (ev_id, _) in enumerate(ranked_b, start=1):
            rrf_scores[ev_id] = rrf_scores.get(ev_id, 0.0) + 1.0 / (_RRF_K + rank)
        return sorted(rrf_scores.items(), key=lambda x: (-x[1], x[0]))

    def answer_query(
        self,
        query: str,
        *,
        scheme_id: str | None = None,
        include_fictional_demo: bool = False,
        top_k: int = 3,
        _fusion_mode: str = "rrf",
    ) -> AskResponse:
        """
        Search verified policy clauses (or explicitly isolated demo clauses) for `query`.

        _fusion_mode controls the retrieval strategy:
          "unigram" — unigram tokens with synonym expansion only
          "bigram"  — unigram + bigram tokens with synonym expansion
          "rrf"     — RRF merge of unigram and bigram ranked lists (default)
        """
        cleaned_query = (query or "").strip()
        if not cleaned_query:
            return AskResponse(
                query=query,
                scheme_id=scheme_id,
                status=RetrievalStatus.NO_RELEVANT_MATCH,
                answer_message="Please enter a non-empty question about scholarship policy.",
                passages=[],
            )

        # Resolve candidate schemes while enforcing strict real-vs-fictional separation
        if scheme_id is not None:
            target = self._schemes_by_id.get(scheme_id)
            if target is None:
                return AskResponse(
                    query=cleaned_query,
                    scheme_id=scheme_id,
                    status=RetrievalStatus.INSUFFICIENT_VERIFIED_EVIDENCE,
                    answer_message=f"Scheme '{scheme_id}' was not found in the active catalogue.",
                    passages=[],
                )
            if target.is_fictional and not include_fictional_demo:
                return AskResponse(
                    query=cleaned_query,
                    scheme_id=scheme_id,
                    status=RetrievalStatus.INSUFFICIENT_VERIFIED_EVIDENCE,
                    answer_message=(
                        f"Scenario '{scheme_id}' is a fictional demo fixture. Set "
                        "include_fictional_demo=True to query fictional demo clauses."
                    ),
                    passages=[],
                )
            candidate_schemes = [target]
        else:
            candidate_schemes = [
                s
                for s in self._schemes_by_id.values()
                if s.is_fictional == include_fictional_demo
            ]

        is_fictional_context = any(s.is_fictional for s in candidate_schemes)
        fictional_warning = FICTIONAL_DEMO_WARNING if is_fictional_context else None

        # Collect eligible evidence documents
        corpus: list[tuple[SchemeRecord, EvidenceReference, list[str]]] = []
        for scheme in candidate_schemes:
            for ev in scheme.evidence_registry.values():
                # Real schemes: only human-verified, non-fictional evidence
                if not scheme.is_fictional and (not ev.verified or ev.fictional):
                    continue
                doc_text = (
                    f"{scheme.name} {ev.source_title} "
                    f"{ev.section_or_page or ''} {ev.excerpt}"
                )
                tokens = tokenize_policy_text(doc_text, include_bigrams=True)
                if tokens:
                    corpus.append((scheme, ev, tokens))

        if not corpus:
            scheme_label = f" for scheme '{scheme_id}'" if scheme_id else ""
            return AskResponse(
                query=cleaned_query,
                scheme_id=scheme_id,
                status=RetrievalStatus.INSUFFICIENT_VERIFIED_EVIDENCE,
                answer_message=(
                    f"No human-verified policy clauses are currently recorded{scheme_label}. "
                    "HaqSetu refuses to guess unverified eligibility limits, deadlines, or "
                    "award amounts. Please consult the official government portal directly."
                ),
                passages=[],
                is_fictional_context=is_fictional_context,
                fictional_warning=fictional_warning,
            )

        # Tokenize query in two ways for RRF
        q_unigram = tokenize_policy_text(cleaned_query, expand_synonyms=True)
        q_bigram = tokenize_policy_text(
            cleaned_query, expand_synonyms=True, include_bigrams=True
        )

        if not q_unigram:
            return AskResponse(
                query=cleaned_query,
                scheme_id=scheme_id,
                status=RetrievalStatus.NO_RELEVANT_MATCH,
                answer_message=(
                    "Your question did not contain searchable policy terms. "
                    "Try asking about marks, family income, enrollment, or concurrent scholarships."
                ),
                passages=[],
                is_fictional_context=is_fictional_context,
                fictional_warning=fictional_warning,
            )

        # Score both runs
        corpus_unigram = [
            (scheme, ev, tokenize_policy_text(
                f"{scheme.name} {ev.source_title} {ev.section_or_page or ''} {ev.excerpt}",
                include_bigrams=False,
            ))
            for scheme, ev, _ in corpus
        ]
        corpus_bigram = corpus  # already tokenised with bigrams

        ranked_u = self._score_corpus(corpus_unigram, q_unigram)
        ranked_b = self._score_corpus(corpus_bigram, q_bigram)

        if _fusion_mode == "unigram":
            final_ranked = ranked_u
        elif _fusion_mode == "bigram":
            final_ranked = ranked_b
        else:  # "rrf" (default)
            final_ranked = self._rrf_merge(ranked_u, ranked_b)

        if not final_ranked:
            # Check if any single-run hit exists below threshold
            q_counts = Counter(
                tok for tok in q_unigram
                if any(tok in Counter(toks) for _, _, toks in corpus_unigram)
            )
            if not q_counts:
                return AskResponse(
                    query=cleaned_query,
                    scheme_id=scheme_id,
                    status=RetrievalStatus.NO_RELEVANT_MATCH,
                    answer_message=(
                        "No recorded policy clause matched your question. HaqSetu only answers "
                        "from explicitly recorded policy excerpts and cannot speculate on topics "
                        "outside the verified evidence registry."
                    ),
                    passages=[],
                    is_fictional_context=is_fictional_context,
                    fictional_warning=fictional_warning,
                )
            return AskResponse(
                query=cleaned_query,
                scheme_id=scheme_id,
                status=RetrievalStatus.NO_RELEVANT_MATCH,
                answer_message=(
                    "No recorded policy passage met the minimum relevance threshold for your "
                    "question. Please check the official portal directly."
                ),
                passages=[],
                is_fictional_context=is_fictional_context,
                fictional_warning=fictional_warning,
            )

        # Build evidence lookup for metadata
        ev_lookup: dict[str, tuple[SchemeRecord, EvidenceReference]] = {
            ev.id: (scheme, ev)
            for scheme, ev, _ in corpus
        }

        scored_passages: list[RetrievedPassage] = []
        for ev_id, score in final_ranked[:max(1, top_k)]:
            pair = ev_lookup.get(ev_id)
            if pair is None:
                continue
            scheme, ev = pair
            scored_passages.append(
                RetrievedPassage(
                    evidence_id=ev.id,
                    scheme_id=scheme.id,
                    scheme_name=scheme.name,
                    source_title=ev.source_title,
                    source_url=ev.source_url,
                    academic_cycle=(
                        ev.academic_cycle
                        or scheme.academic_year_verified
                        or scheme.academic_year
                    ),
                    section_or_page=ev.section_or_page,
                    excerpt=ev.excerpt,
                    similarity_score=round(score, 4),
                    verified=ev.verified,
                    is_fictional=scheme.is_fictional or ev.fictional,
                )
            )

        if not scored_passages:
            return AskResponse(
                query=cleaned_query,
                scheme_id=scheme_id,
                status=RetrievalStatus.NO_RELEVANT_MATCH,
                answer_message=(
                    "No recorded policy passage met the minimum relevance threshold for your "
                    "question. Please check the official portal directly."
                ),
                passages=[],
                is_fictional_context=is_fictional_context,
                fictional_warning=fictional_warning,
            )

        best = scored_passages[0]
        prefix = "[FICTIONAL DEMO CLAUSE] " if best.is_fictional else ""
        answer_msg = (
            f"{prefix}Retrieved {len(scored_passages)} supporting clause(s). "
            f"Top match ({best.source_title}): '{best.excerpt}'"
        )

        return AskResponse(
            query=cleaned_query,
            scheme_id=scheme_id,
            status=RetrievalStatus.SUPPORTED_MATCH,
            answer_message=answer_msg,
            passages=scored_passages,
            is_fictional_context=is_fictional_context,
            fictional_warning=fictional_warning,
            method_disclaimer=RETRIEVAL_METHOD_DISCLAIMER,
        )
