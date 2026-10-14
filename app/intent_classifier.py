"""
Multinomial Naive Bayes intent classifier for HaqSetu Stage P9.

Uses Python standard library only (math, re, collections, json).
Trained on-the-fly from data/ml/intent_dataset.json at import/init time.

Honesty constraints (per audit):
- Confidence scores are softmax-normalised log-probabilities over this small
  synthetic dataset. They reflect RELATIVE class ranking, not calibrated
  posterior probabilities.
- The classifier is trained on 160 synthetic utterances. Do not claim
  high-accuracy production NLU based on this dataset size.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.schemas import INTENT_CONFIDENCE_NOTICE, IntentClass, IntentPrediction

_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "am", "an", "and", "are", "as", "at", "be", "by", "can", "do",
        "does", "for", "from", "how", "i", "if", "in", "is", "it", "me",
        "my", "of", "on", "or", "should", "that", "the", "their", "this",
        "to", "was", "what", "when", "where", "which", "who", "will", "with",
        "would", "you", "your",
    }
)

DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "ml" / "intent_dataset.json"
)

# Smoothing parameter for Laplace / add-alpha smoothing
_ALPHA = 1.0


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, remove stopwords; return unigrams."""
    cleaned = text.lower()
    tokens = re.findall(r"[a-z0-9]+", cleaned)
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


def _softmax(log_scores: dict[str, float]) -> dict[str, float]:
    """
    Softmax over log-probability sums.

    Returns scores in [0, 1] summing to 1.0.
    Note: this is a convenience normalisation for display; it does NOT yield
    calibrated posterior probabilities.
    """
    vals = list(log_scores.values())
    max_val = max(vals)
    exp_vals = {k: math.exp(v - max_val) for k, v in log_scores.items()}
    total = sum(exp_vals.values())
    return {k: round(v / total, 6) for k, v in exp_vals.items()}


class NaiveBayesIntentClassifier:
    """
    Multinomial Naive Bayes text classifier with Laplace smoothing.

    Trained in-memory from a JSON utterance file; no external ML libraries.
    """

    def __init__(self, dataset_path: str | Path = DEFAULT_DATASET_PATH) -> None:
        self._class_log_prior: dict[str, float] = {}
        self._feature_log_prob: dict[str, dict[str, float]] = {}
        self._vocab: frozenset[str] = frozenset()
        self._classes: list[str] = []
        self._trained: bool = False
        self._dataset_path = Path(dataset_path)
        if self._dataset_path.exists():
            self.train(self._dataset_path)

    def train(self, dataset_path: str | Path) -> dict[str, Any]:
        """
        Train the classifier from a JSON file and return a training report.

        The JSON file must have an 'utterances' list where each item has
        'text' (str) and 'intent' (str) fields.
        """
        path = Path(dataset_path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        utterances = raw.get("utterances", [])

        # Collect per-class token counts
        class_counts: Counter[str] = Counter()
        class_token_counts: dict[str, Counter[str]] = defaultdict(Counter)
        all_tokens: set[str] = set()

        for item in utterances:
            text = str(item.get("text", ""))
            intent = str(item.get("intent", ""))
            tokens = _tokenize(text)
            class_counts[intent] += 1
            for tok in tokens:
                class_token_counts[intent][tok] += 1
                all_tokens.add(tok)

        self._vocab = frozenset(all_tokens)
        vocab_size = len(self._vocab)
        total_docs = sum(class_counts.values())
        self._classes = sorted(class_counts.keys())

        # Log prior: log P(class)
        self._class_log_prior = {
            cls: math.log(count / total_docs)
            for cls, count in class_counts.items()
        }

        # Log likelihood: log P(token | class) with Laplace smoothing
        self._feature_log_prob = {}
        for cls in self._classes:
            tok_counter = class_token_counts[cls]
            total_tokens_in_class = sum(tok_counter.values()) + _ALPHA * vocab_size
            log_probs: dict[str, float] = {}
            for tok in self._vocab:
                count = tok_counter.get(tok, 0)
                log_probs[tok] = math.log((count + _ALPHA) / total_tokens_in_class)
            # Store the smoothed log-prob for unknown tokens (not in query vocab)
            log_probs["__unk__"] = math.log(_ALPHA / total_tokens_in_class)
            self._feature_log_prob[cls] = log_probs

        self._trained = True
        return {
            "total_utterances": total_docs,
            "classes": self._classes,
            "vocab_size": vocab_size,
        }

    def predict(self, text: str) -> IntentPrediction:
        """
        Predict the intent of `text`.

        Returns an IntentPrediction with softmax-normalised confidence scores.
        If the classifier has not been trained (dataset file absent), returns
        OUT_OF_SCOPE with a notice.
        """
        if not self._trained:
            return IntentPrediction(
                predicted_intent=IntentClass.OUT_OF_SCOPE,
                confidence_scores={c.value: 0.0 for c in IntentClass},
                confidence_notice=(
                    "Classifier not trained: dataset file not found. "
                    + INTENT_CONFIDENCE_NOTICE
                ),
                is_out_of_scope=True,
            )

        tokens = _tokenize(text)
        log_scores: dict[str, float] = {}

        for cls in self._classes:
            log_p = self._class_log_prior[cls]
            cls_log_probs = self._feature_log_prob[cls]
            unk_log_prob = cls_log_probs["__unk__"]
            for tok in tokens:
                log_p += cls_log_probs.get(tok, unk_log_prob)
            log_scores[cls] = log_p

        soft_scores = _softmax(log_scores)
        best_class = max(soft_scores, key=lambda k: soft_scores[k])

        # Map string class name to IntentClass enum
        try:
            predicted = IntentClass(best_class)
        except ValueError:
            predicted = IntentClass.OUT_OF_SCOPE

        return IntentPrediction(
            predicted_intent=predicted,
            confidence_scores=soft_scores,
            is_out_of_scope=(predicted == IntentClass.OUT_OF_SCOPE),
        )

    def evaluate(self, test_utterances: list[dict[str, str]]) -> dict[str, Any]:
        """
        Evaluate the classifier on a list of {'text': ..., 'intent': ...} dicts.

        Returns per-class precision/recall/F1 and overall accuracy.
        Note: training and test data share the same synthetic dataset in this MVP;
        this is an in-sample smoke-test, not independent validation.
        """
        if not self._trained:
            return {"error": "Classifier not trained."}

        true_labels: list[str] = []
        pred_labels: list[str] = []

        for item in test_utterances:
            true_labels.append(item["intent"])
            pred_labels.append(self.predict(item["text"]).predicted_intent.value)

        correct = sum(t == p for t, p in zip(true_labels, pred_labels))
        accuracy = round(correct / len(true_labels), 4) if true_labels else 0.0

        classes = sorted(set(true_labels))
        per_class: dict[str, dict[str, float]] = {}
        for cls in classes:
            tp = sum(t == cls and p == cls for t, p in zip(true_labels, pred_labels))
            fp = sum(t != cls and p == cls for t, p in zip(true_labels, pred_labels))
            fn = sum(t == cls and p != cls for t, p in zip(true_labels, pred_labels))
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            f1 = (
                2 * precision * recall / (precision + recall)
                if (precision + recall)
                else 0.0
            )
            per_class[cls] = {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "support": tp + fn,
            }

        macro_f1 = round(
            sum(v["f1"] for v in per_class.values()) / len(per_class), 4
        ) if per_class else 0.0

        return {
            "total_samples": len(true_labels),
            "accuracy": accuracy,
            "macro_f1": macro_f1,
            "per_class": per_class,
            "note": (
                "In-sample evaluation on the same synthetic dataset used for training. "
                "This is a smoke-test for correct training logic, not independent validation. "
                "Do not interpret these figures as generalisation accuracy."
            ),
        }
