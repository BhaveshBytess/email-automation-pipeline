"""
MiniLM job ranker for the Cold Email Pipeline.

Module 5 responsibilities:
- Load all-MiniLM-L6-v2 model once per run
- Build resume embedding
- Score jobs with cosine similarity
- Select top-N jobs (default 25)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sentence_transformers import SentenceTransformer

RESUME_BULLETS: list[str] = [
    "Built temporal GNN TRDGNN achieving 0.58 PR-AUC on 203K-node fraud detection graph PyTorch Geometric XGBoost.",
    "PDF-to-JSON pipeline 100% JSON validity 81% evidence precision LLMs Pydantic Gemma DeepSeek Python Streamlit.",
    "10x GNN parameter reduction 500K to 50K with 108% performance gain resource-constrained systems.",
    "Python PyTorch PyG TensorFlow scikit-learn Docker Git Linux Streamlit Pydantic NumPy Pandas.",
    "CS undergrad IIIT Kota GNNs unstructured data pipelines production ML full test coverage reproducible research.",
]

DEFAULT_RESUME_TEXT: str = " ".join(RESUME_BULLETS)


@lru_cache(maxsize=1)
def load_model() -> SentenceTransformer:
    """Load and cache the sentence-transformers model for the run."""
    return SentenceTransformer("all-MiniLM-L6-v2")


def get_resume_embedding(
    resume_text: str,
    model: SentenceTransformer,
) -> NDArray[np.float64]:
    """Encode resume text into a normalized embedding vector."""
    embedding = model.encode(
        resume_text,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return np.asarray(embedding, dtype=np.float64)


def _job_text(job: dict[str, Any]) -> str:
    """Build ranker input text: title + company + jd_summary."""
    return (
        f"{job.get('title', '')} "
        f"{job.get('company', '')} "
        f"{job.get('jd_summary', '')}"
    ).strip()


def _cosine_score_0_1(
    a: NDArray[np.float64],
    b: NDArray[np.float64],
) -> float:
    """Return cosine similarity clamped to [0.0, 1.0]."""
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    score = float(np.dot(a, b) / denom)
    return max(0.0, min(1.0, score))


def rank_jobs(
    jobs: list[dict[str, Any]],
    resume_embedding: NDArray[np.float64],
    model: SentenceTransformer,
) -> list[dict[str, Any]]:
    """Attach relevance_score to jobs and return score-descending list."""
    if not jobs:
        return []

    job_texts = [_job_text(job) for job in jobs]
    job_embeddings = model.encode(
        job_texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    scored_jobs: list[dict[str, Any]] = []
    resume_vec = np.asarray(resume_embedding, dtype=np.float64)

    for job, job_vec in zip(jobs, job_embeddings):
        score = _cosine_score_0_1(resume_vec, np.asarray(job_vec, dtype=np.float64))
        with_score = dict(job)
        with_score["relevance_score"] = score
        scored_jobs.append(with_score)

    scored_jobs.sort(key=lambda x: float(x["relevance_score"]), reverse=True)
    return scored_jobs


def select_top_n(ranked_jobs: list[dict[str, Any]], n: int = 25) -> list[dict[str, Any]]:
    """Return top N ranked jobs, bounded by list length."""
    if n <= 0:
        return []
    return ranked_jobs[: min(n, len(ranked_jobs))]
