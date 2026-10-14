# HaqSetu Stage P9 — AI/ML Model Card (`MODEL_CARD.md`)

**Date:** 2025-07-14  
**Package:** HaqSetu — AI Welfare and Scholarship Navigator (Stage P9)  
**Primary SDG:** SDG 4 (Quality Education)

---

## Honesty Statement

All three AI/ML components in Stage P9 use Python standard-library implementations only
(math, re, collections, json). No external ML frameworks, pre-trained models, or LLMs are
used. All benchmark metrics below were measured on **synthetic, in-distribution datasets
designed alongside the models**. They verify correct implementation logic and do not
constitute independent validation of generalisation accuracy on unseen real-world queries.

---

## 1. Intent Classifier (Multinomial Naive Bayes)

| Property | Value |
|---|---|
| Algorithm | Multinomial Naive Bayes with Laplace (add-α=1) smoothing |
| Training data | 160 synthetic utterances, 8 classes (20 per class) |
| Tokenization | Lowercase unigrams, stopword removal |
| Library | Python standard library only (math, re, collections, json) |
| Dataset file | `data/ml/intent_dataset.json` |
| Source module | `app/intent_classifier.py` |

**Intended use:** Route user queries within the HaqSetu scholarship navigator to the
appropriate API endpoint (eligibility check, scheme discovery, Q&A, etc.).

**NOT intended for:** Any eligibility determination, sensitive government policy interpretation,
or deployment outside the HaqSetu navigation context.

**Confidence scores:** The output `confidence_scores` are softmax-normalised log-probability
sums over the Naive Bayes log-likelihoods. They reflect relative class ranking within the
classifier's distribution, **not calibrated posterior probabilities**.

### In-Sample Benchmark (smoke-test only)

> ⚠️ Same dataset used for training and evaluation. These metrics test implementation
> correctness, not generalisation.

| Metric | Value |
|---|---|
| Total samples | 160 |
| In-sample accuracy | 0.9812 |
| Macro F1 | 0.9814 |

Per-class (in-sample):

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| ask_award | 1.000 | 1.000 | 1.000 | 20 |
| ask_deadline | 1.000 | 0.950 | 0.974 | 20 |
| ask_documents | 0.952 | 1.000 | 0.976 | 20 |
| ask_grievance | 1.000 | 0.950 | 0.974 | 20 |
| ask_portal | 0.905 | 0.950 | 0.927 | 20 |
| check_eligibility | 1.000 | 1.000 | 1.000 | 20 |
| find_scheme | 1.000 | 1.000 | 1.000 | 20 |
| out_of_scope | 1.000 | 1.000 | 1.000 | 20 |

---

## 2. Policy Clause Retriever (TF-IDF + RRF)

| Property | Value |
|---|---|
| Algorithm | Smoothed TF-IDF cosine similarity with unigram + bigram tokenization and Reciprocal Rank Fusion (RRF, k=60) |
| Vocabulary | Unigrams + adjacent bigrams over policy evidence excerpts |
| Synonym expansion | Domain synonym map (salary→income, percentage→marks/qualifying, etc.) |
| Audit fix (P9) | Removed "80" from percentage synonyms — numeric thresholds must not be injected as retrieval tokens |
| Evidence corpus | Only human-verified (`verified=True`, `fictional=False`) evidence from `evidence_registry` |
| Threshold | cosine ≥ 0.16 (configurable) |
| Source module | `app/retriever.py` |
| Eval corpus | `data/eval_queries.json` (10 synthetic queries) |

**Intended use:** Source-grounded policy Q&A over recorded, human-verified evidence excerpts.

**NOT intended for:** Eligibility determination. Retrieving a passage never evaluates or
confirms applicant eligibility.

**Refusal guarantee:** Unverified real schemes (`verified=False` evidence) always return
`INSUFFICIENT_VERIFIED_EVIDENCE`. The retriever never fabricates policy details.

### Retrieval Benchmark (10 synthetic queries, in-distribution)

| Metric | Value |
|---|---|
| Total queries | 10 |
| Supported queries | 6 |
| Refusal queries | 4 |
| Top-1 Accuracy | 1.0000 |
| Top-3 Recall | 1.0000 |
| Mean Reciprocal Rank | 1.0000 |
| Refusal Accuracy | 1.0000 |

### Ablation Study (unigram vs bigram vs RRF)

| Mode | Top-1 | Top-3 | MRR |
|---|---|---|---|
| unigram | 1.0000 | 1.0000 | 1.0000 |
| bigram | 1.0000 | 1.0000 | 1.0000 |
| rrf | 1.0000 | 1.0000 | 1.0000 |

The eval-02 query was updated (from "How much marks score do I need in my qualifying examination?"
to "What score percentage is needed in 12th board?") to test synonym expansion and bigram matching
for the word "percentage" without injecting numeric "80" tokens.

---

## 3. Scheme Recommender (Content-Based TF-IDF)

| Property | Value |
|---|---|
| Algorithm | TF-IDF cosine similarity over curated scheme descriptor text + bigrams |
| Descriptors | `_CURATED_SCHEME_DESCRIPTORS` in `app/recommender.py` — catalogue metadata only, NOT eligibility rules |
| Source module | `app/recommender.py` |
| Eval corpus | `data/ml/recommendation_eval.json` (12 synthetic queries) |

**Intended use:** Suggest relevant schemes for a user's free-text query based on keyword
similarity to scheme names, issuing bodies, and descriptive metadata.

**NOT intended for:** Eligibility assessment. Recommendation scores reflect metadata keyword
overlap, not policy rule evaluation. The `RECOMMENDATION_NON_ELIGIBILITY_DISCLAIMER` in every
response enforces this boundary.

**Descriptor honesty:** `_CURATED_SCHEME_DESCRIPTORS` contains non-authoritative descriptive
strings derived from official portal names and scheme short names. These are catalogue metadata
used to improve keyword coverage for recommendation only. They do not represent verified
eligibility policy.

### Recommendation Benchmark (12 synthetic queries, in-distribution)

| Metric | Value |
|---|---|
| Total queries | 12 |
| Top-1 Accuracy | 1.0000 |
| Mean Reciprocal Rank | 1.0000 |

---

## Known Limitations

1. **Small synthetic training data:** All three models were trained and evaluated on small
   synthetic datasets (160 utterances for classification; 10-12 queries for retrieval/recommendation).
   Performance on genuinely unseen real-world queries is unknown.

2. **In-sample evaluation:** The reported metrics measure implementation correctness on
   data designed alongside the models, not independent generalisation.

3. **No semantic understanding:** All models use term-frequency statistics. They cannot
   handle paraphrases, negation, or implicit intent that requires semantic reasoning.

4. **Confidence ≠ probability:** Intent classifier confidence scores are softmax-normalised
   log-likelihoods. They are NOT calibrated probabilities.

5. **Real schemes remain LISTING_ONLY:** No real scheme eligibility can be assessed until
   human policy verification is completed per `DATA_VERIFICATION.md`.

6. **No external validation:** No human evaluation or independent test set was used for
   any of the three P9 models.
