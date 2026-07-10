from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "mcp" / "tests" / "fixtures" / "retrieval-quality.json"
MODEL_MANIFEST = ROOT / "third_party" / "model-manifest.json"


def _artifact_stats(root: Path) -> tuple[int, int, str]:
    records = []
    for path in root.rglob("*"):
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            records.append(
                (relative, hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size)
            )
    records.sort()
    tree_hash = hashlib.sha256(
        "".join(f"{digest}  {relative}\n" for relative, digest, _ in records).encode()
    ).hexdigest()
    return len(records), sum(size for _, _, size in records), tree_hash


def test_model_manifest_pins_artifact_license_dimensions_and_corpus() -> None:
    manifest = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
    corpus_hash = hashlib.sha256(DATASET.read_bytes()).hexdigest()
    artifact = ROOT / manifest["artifact"]["path"]

    assert manifest["model_id"] == "intfloat/multilingual-e5-small"
    assert manifest["revision"] == "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    assert manifest["license"] == "MIT"
    assert manifest["dimensions"] == 384
    assert manifest["query_prefix"] == "query: "
    assert manifest["document_prefix"] == "passage: "
    assert manifest["artifact"]["tree_sha256"] == (
        "c78988c745782001597db940ddbb894357f130867dc77a4e13a5d5512b50c2c4"
    )
    assert _artifact_stats(artifact) == (
        manifest["artifact"]["file_count"],
        manifest["artifact"]["bytes"],
        manifest["artifact"]["tree_sha256"],
    )
    assert manifest["corpus"]["sha256"] == corpus_hash
    for result in manifest["metrics"].values():
        assert result["hit_at_3"] >= 0.95
        assert result["mrr"] >= 0.90


def evaluate_model(
    model_name_or_path: str,
    *,
    query_prefix: str = "",
    document_prefix: str = "",
) -> dict[str, dict[str, float]]:
    from sentence_transformers import SentenceTransformer

    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    model = SentenceTransformer(model_name_or_path)
    documents = dataset["documents"]
    doc_ids = [item["id"] for item in documents]
    doc_vectors = model.encode(
        [document_prefix + item["text"] for item in documents],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    metrics: dict[str, dict[str, float]] = {}
    for suite, cases in dataset["suites"].items():
        corpus_prefix = dataset["suite_corpora"][suite]
        corpus_rows = [index for index, doc_id in enumerate(doc_ids) if doc_id.startswith(corpus_prefix)]
        query_vectors = model.encode(
            [query_prefix + case["query"] for case in cases],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        ranks = []
        for case, query_vector in zip(cases, query_vectors, strict=True):
            order = np.argsort(-(doc_vectors[corpus_rows] @ query_vector))
            ranked_ids = [doc_ids[corpus_rows[row]] for row in order]
            ranks.append(ranked_ids.index(case["target"]) + 1)
        metrics[suite] = {
            "hit_at_3": sum(rank <= 3 for rank in ranks) / len(ranks),
            "mrr": sum(1.0 / rank for rank in ranks) / len(ranks),
        }
    return metrics


@pytest.mark.skipif(
    os.environ.get("EVERMIND_RUN_MODEL_QUALITY") != "1",
    reason="set EVERMIND_RUN_MODEL_QUALITY=1 for the pinned local-model gate",
)
def test_pinned_local_model_meets_retrieval_quality_gate() -> None:
    manifest = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
    model_path = os.environ.get("EVERMIND_LOCAL_MODEL_PATH") or manifest["model_id"]
    metrics = evaluate_model(
        model_path,
        query_prefix=manifest.get("query_prefix", ""),
        document_prefix=manifest.get("document_prefix", ""),
    )

    for suite, result in metrics.items():
        assert result["hit_at_3"] >= 0.95, (suite, result)
        assert result["mrr"] >= 0.90, (suite, result)
