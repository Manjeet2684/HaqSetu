"""
Content-based TF-IDF scheme recommender for HaqSetu Stage P9.

Uses Python standard library only (math, re, collections).

Honesty constraints (per audit):
- _CURATED_SCHEME_DESCRIPTORS contains descriptive catalogue metadata derived
  from public scheme names, issuing bodies, and portal labels. It is NOT
  verified eligibility policy. It exists solely to improve keyword matching
  for recommendation, not to establish any eligibility rule.
- Recommendation scores represent keyword similarity between the user's query
  and the scheme descriptor text, not eligibility assessment.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from app.schemas import (
    RECOMMENDATION_NON_ELIGIBILITY_DISCLAIMER,
    SchemeDataType,
    SchemeReadiness,
    SchemeRecommendationItem,
    SchemeRecord,
)

_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "am", "an", "and", "are", "as", "at", "be", "by", "can", "do",
        "does", "for", "from", "how", "i", "if", "in", "is", "it", "me",
        "my", "of", "on", "or", "should", "that", "the", "their", "this",
        "to", "was", "what", "when", "where", "which", "who", "will", "with",
        "would", "you", "your",
    }
)

# ---------------------------------------------------------------------------
# Curated scheme descriptor vocabulary
# ---------------------------------------------------------------------------
# These are non-authoritative descriptive metadata strings derived from
# official portal names, scheme short names, and issuing body labels in
# data/schemes.json. They improve term coverage for recommendation only.
# THEY DO NOT REPRESENT VERIFIED ELIGIBILITY RULES.
# ---------------------------------------------------------------------------
_CURATED_SCHEME_DESCRIPTORS: dict[str, str] = {
    "pmsp-central-sector": (
        "central sector scheme scholarship college university students "
        "Ministry Education higher education fresh renewal "
        "national scholarship portal NSP scholarships.gov.in "
        "undergraduate postgraduate degree bsc ba bcom btech "
        "after class 12 qualifying examination parental income "
        "UGC recognised institution merit based award OTR registration "
        "central government scholarship fresh applicant"
    ),
    "up-pre-matric-scholarship": (
        "uttar pradesh pre-matric scholarship school student "
        "class 9 10 state government social welfare department "
        "scholarship.up.gov.in backward classes SC ST OBC minority "
        "shasanadesh government order pre matric school fee reimbursement "
        "UP state scholarship girl student caste income district "
        "social welfare backward class welfare department UP"
    ),
    "demo-assessable": (
        "fictional demo imaginary merit scholarship demonstration "
        "test scenario invented rules synthetic persona fictional authority "
        "demo assessment example qualifying marks family income enrollment "
        "concurrent scholarship fictional evidence"
    ),
    "demo-listing-only": (
        "fictional demo listing only real stub candidate "
        "unverified scheme listing demo fixture reference"
    ),
}

DEFAULT_SIMILARITY_THRESHOLD = 0.08


def _tokenize_for_recommend(text: str) -> list[str]:
    """
    Tokenize recommendation query/descriptor text to lowercase unigrams and
    adjacent bigrams, filtering stopwords.
    """
    cleaned = text.lower()
    raw_tokens = re.findall(r"[a-z0-9]+", cleaned)
    unigrams = [t for t in raw_tokens if t not in _STOPWORDS and len(t) > 1]
    bigrams = [f"{unigrams[i]}_{unigrams[i+1]}" for i in range(len(unigrams) - 1)]
    return unigrams + bigrams


def _build_tfidf_vector(
    tokens: list[str],
    idf: dict[str, float],
) -> dict[str, float]:
    """Build an L2-normalised TF-IDF vector from a token list and IDF map."""
    counts = Counter(tokens)
    weights = {
        tok: (1.0 + math.log(freq)) * idf.get(tok, 1.0)
        for tok, freq in counts.items()
        if tok in idf
    }
    norm = math.sqrt(sum(w * w for w in weights.values()))
    if norm == 0.0:
        return {}
    return {tok: w / norm for tok, w in weights.items()}


class SchemeRecommender:
    """
    TF-IDF content-based scheme recommender.

    Builds an in-memory descriptor corpus from curated scheme metadata and
    the catalogue's own scheme name/issuing body fields. Recommendation is
    based solely on keyword similarity and never on eligibility rules.
    """

    def __init__(
        self,
        schemes: list[SchemeRecord],
        *,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> None:
        self._threshold = similarity_threshold
        self._corpus: list[tuple[SchemeRecord, list[str]]] = []
        self._idf: dict[str, float] = {}
        self._build_index(schemes)

    def _build_index(self, schemes: list[SchemeRecord]) -> None:
        """Tokenise each scheme descriptor and compute smoothed corpus IDF."""
        tokenised: list[tuple[SchemeRecord, list[str]]] = []
        for scheme in schemes:
            # Combine curated descriptor with live catalogue fields
            curated = _CURATED_SCHEME_DESCRIPTORS.get(scheme.id, "")
            live_text = f"{scheme.name} {scheme.short_name} {scheme.issuing_body}"
            combined = f"{live_text} {curated}"
            tokens = _tokenize_for_recommend(combined)
            if tokens:
                tokenised.append((scheme, tokens))

        self._corpus = tokenised
        num_docs = len(tokenised)

        # Compute smoothed IDF across the descriptor corpus
        doc_freq: Counter[str] = Counter()
        for _, toks in tokenised:
            for tok in set(toks):
                doc_freq[tok] += 1

        self._idf = {
            tok: math.log((1.0 + num_docs) / (1.0 + df)) + 1.0
            for tok, df in doc_freq.items()
        }

    def recommend(
        self,
        query: str,
        *,
        top_k: int = 3,
        include_fictional: bool = False,
    ) -> list[SchemeRecommendationItem]:
        """
        Return top-k scheme recommendations for `query`.

        Schemes are filtered by is_fictional unless include_fictional=True.
        Returns an empty list if no scheme exceeds the similarity threshold.
        """
        query_tokens = _tokenize_for_recommend(query)
        if not query_tokens:
            return []

        # Build query vector from corpus IDF (only terms that appear in corpus)
        q_counts = Counter(tok for tok in query_tokens if tok in self._idf)
        if not q_counts:
            return []

        q_weights_raw = {
            tok: (1.0 + math.log(freq)) * self._idf[tok]
            for tok, freq in q_counts.items()
        }
        q_norm = math.sqrt(sum(w * w for w in q_weights_raw.values()))
        if q_norm == 0.0:
            return []
        q_weights = {tok: w / q_norm for tok, w in q_weights_raw.items()}

        scored: list[SchemeRecommendationItem] = []
        for scheme, doc_tokens in self._corpus:
            if not include_fictional and scheme.is_fictional:
                continue

            d_vec = _build_tfidf_vector(doc_tokens, self._idf)
            cosine = sum(q_weights.get(tok, 0.0) * d_vec.get(tok, 0.0) for tok in q_weights)

            if cosine >= self._threshold:
                top_matches = sorted(
                    (tok for tok in q_weights if tok in d_vec),
                    key=lambda t: q_weights[t] * d_vec[t],
                    reverse=True,
                )[:3]
                match_reason = (
                    f"Matched on: {', '.join(top_matches)}" if top_matches else "General match"
                )
                scored.append(
                    SchemeRecommendationItem(
                        scheme_id=scheme.id,
                        scheme_name=scheme.name,
                        short_name=scheme.short_name,
                        issuing_body=scheme.issuing_body,
                        portal_url=scheme.portal_url,
                        readiness=scheme.readiness,
                        data_type=scheme.data_type,
                        is_fictional=scheme.is_fictional,
                        similarity_score=round(cosine, 4),
                        match_reason=match_reason,
                    )
                )

        scored.sort(key=lambda x: (-x.similarity_score, x.scheme_id))
        return scored[:top_k]

    def evaluate_benchmark(
        self, benchmark_path: str | Any
    ) -> dict[str, Any]:
        """
        Run the recommendation benchmark from data/ml/recommendation_eval.json.

        Returns top-1 accuracy and mean reciprocal rank over the 12 synthetic
        queries. These are in-distribution smoke metrics only.
        """
        import json
        from pathlib import Path

        path = Path(benchmark_path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        queries = raw.get("queries", [])

        top1_hits = 0
        reciprocal_ranks: list[float] = []

        for item in queries:
            recs = self.recommend(item["query"], top_k=5, include_fictional=False)
            ids = [r.scheme_id for r in recs]
            expected = item["expected_top_id"]

            if ids and ids[0] == expected:
                top1_hits += 1

            if expected in ids:
                rank = ids.index(expected) + 1
                reciprocal_ranks.append(1.0 / rank)
            else:
                reciprocal_ranks.append(0.0)

        total = len(queries)
        return {
            "total_queries": total,
            "top1_accuracy": round(top1_hits / total, 4) if total else 0.0,
            "mean_reciprocal_rank": (
                round(sum(reciprocal_ranks) / total, 4) if total else 0.0
            ),
            "note": (
                "Synthetic in-distribution smoke benchmark (12 queries). "
                "Queries were designed with the catalogue in mind; these metrics "
                "should not be interpreted as independent generalisation accuracy. "
                + RECOMMENDATION_NON_ELIGIBILITY_DISCLAIMER
            ),
        }
