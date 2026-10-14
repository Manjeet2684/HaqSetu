"""
HaqSetu Stage P9 — ML training, evaluation, and benchmark runner.

Usage:
    python scripts/train_evaluate_ml.py

Prints a concise benchmark report for all three ML components:
  1. Intent Classifier (Multinomial Naive Bayes) — in-sample accuracy
  2. Policy Clause Retriever — 10-query synthetic benchmark (Top-1, Top-3, MRR, Refusal)
  3. Retrieval Ablation — unigram vs bigram vs RRF comparison
  4. Scheme Recommender — 12-query synthetic benchmark (Top-1, MRR)

All metrics are SYNTHETIC SMOKE BENCHMARKS on datasets designed alongside the models.
They verify correct implementation logic. They do not claim generalisation accuracy
on unseen real-world scholarship questions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure repository root is on sys.path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from app.catalog import SchemeCatalogService
from app.retriever import evaluate_retrieval_benchmark, evaluate_retrieval_ablation


def _hr(char: str = "-", width: int = 70) -> str:
    return char * width


def main() -> None:
    print(_hr("="))
    print("HaqSetu Stage P9 — AI/ML Benchmark Report")
    print(_hr("="))
    print(
        "NOTICE: All metrics are synthetic smoke benchmarks.\n"
        "In-sample evaluation on datasets designed alongside the models.\n"
        "Do not interpret as independent generalisation accuracy.\n"
    )

    catalog = SchemeCatalogService()

    # ------------------------------------------------------------------
    # 1. Intent Classifier — in-sample evaluation
    # ------------------------------------------------------------------
    print(_hr())
    print("1. INTENT CLASSIFIER (Multinomial Naive Bayes)")
    print(_hr())

    clf = catalog.classifier
    if clf is None or not clf._trained:
        print("  SKIPPED — classifier not trained (dataset file absent?)")
    else:
        dataset_path = repo_root / "data" / "ml" / "intent_dataset.json"
        raw = json.loads(dataset_path.read_text(encoding="utf-8"))
        report = clf.evaluate(raw.get("utterances", []))
        print(f"  Total samples    : {report['total_samples']}")
        print(f"  In-sample accuracy : {report['accuracy']:.4f}")
        print(f"  Macro F1          : {report['macro_f1']:.4f}")
        print()
        print("  Per-class breakdown:")
        for cls, metrics in sorted(report["per_class"].items()):
            print(
                f"    {cls:<25} P={metrics['precision']:.3f}  "
                f"R={metrics['recall']:.3f}  F1={metrics['f1']:.3f}  "
                f"n={metrics['support']}"
            )
        print()
        print(f"  NOTE: {report['note']}")

    # ------------------------------------------------------------------
    # 2. Policy Retrieval Benchmark
    # ------------------------------------------------------------------
    print()
    print(_hr())
    print("2. POLICY RETRIEVAL BENCHMARK (TF-IDF + RRF, 10 synthetic queries)")
    print(_hr())

    eval_path = repo_root / "data" / "eval_queries.json"
    if not eval_path.exists():
        print("  SKIPPED — eval_queries.json not found")
    else:
        rb = evaluate_retrieval_benchmark(catalog.retriever, eval_path)
        print(f"  Total queries       : {rb['total_queries']}")
        print(f"  Supported queries   : {rb['supported_queries']}")
        print(f"  Refusal queries     : {rb['refusal_queries']}")
        print(f"  Top-1 Accuracy      : {rb['top1_accuracy']:.4f}")
        print(f"  Top-3 Recall        : {rb['top3_recall']:.4f}")
        print(f"  Mean Reciprocal Rank: {rb['mean_reciprocal_rank']:.4f}")
        print(f"  Refusal Accuracy    : {rb['refusal_accuracy']:.4f}")
        print(f"  NOTE: {rb['note']}")

    # ------------------------------------------------------------------
    # 3. Retrieval Ablation (unigram vs bigram vs RRF)
    # ------------------------------------------------------------------
    print()
    print(_hr())
    print("3. RETRIEVAL ABLATION (unigram vs bigram vs RRF)")
    print(_hr())

    if not eval_path.exists():
        print("  SKIPPED — eval_queries.json not found")
    else:
        abl = evaluate_retrieval_ablation(catalog.retriever, eval_path)
        print(f"  Supported queries evaluated: {abl['queries_evaluated']}")
        print()
        header = f"  {'Mode':<10} {'Top-1':>7} {'Top-3':>7} {'MRR':>7}"
        print(header)
        print("  " + "-" * 35)
        for mode in ("unigram", "bigram", "rrf"):
            m = abl["modes"][mode]
            print(
                f"  {mode:<10} {m['top1_accuracy']:>7.4f} {m['top3_recall']:>7.4f} {m['mrr']:>7.4f}"
            )

    # ------------------------------------------------------------------
    # 4. Scheme Recommender Benchmark
    # ------------------------------------------------------------------
    print()
    print(_hr())
    print("4. SCHEME RECOMMENDER BENCHMARK (TF-IDF, 12 synthetic queries)")
    print(_hr())

    rec_eval_path = repo_root / "data" / "ml" / "recommendation_eval.json"
    rec = catalog.recommender
    if rec is None or not rec_eval_path.exists():
        print("  SKIPPED — recommender not available or eval file absent")
    else:
        rec_report = rec.evaluate_benchmark(rec_eval_path)
        print(f"  Total queries       : {rec_report['total_queries']}")
        print(f"  Top-1 Accuracy      : {rec_report['top1_accuracy']:.4f}")
        print(f"  Mean Reciprocal Rank: {rec_report['mean_reciprocal_rank']:.4f}")
        print(f"  NOTE: {rec_report['note'][:120]}...")

    print()
    print(_hr("="))
    print("Benchmark run complete.")
    print(
        "These are in-distribution smoke benchmarks only. See MODEL_CARD.md for full details."
    )
    print(_hr("="))


if __name__ == "__main__":
    main()
