"""Tests for Module 5 — MiniLM ranker.

All tests mock model encoding; no real model download is performed.
"""

import numpy as np

from src.ranker.minilm import DEFAULT_RESUME_TEXT, rank_jobs, select_top_n


class MockSentenceTransformer:
    """Mock model that returns deterministic vectors and records inputs."""

    def __init__(self, vectors: list[list[float]]):
        self.vectors = [np.array(v, dtype=np.float64) for v in vectors]
        self.last_inputs = None

    def encode(self, inputs, convert_to_numpy=True, normalize_embeddings=True):
        self.last_inputs = inputs
        if isinstance(inputs, str):
            return np.array([1.0, 0.0, 0.0], dtype=np.float64)
        return np.array(self.vectors[: len(inputs)], dtype=np.float64)


def _sample_jobs() -> list[dict]:
    return [
        {
            "title": "ML Engineer",
            "company": "Acme",
            "jd_summary": "Graph models and fraud detection",
            "job_id": "j1",
        },
        {
            "title": "Backend Engineer",
            "company": "Beta",
            "jd_summary": "APIs and database scaling",
            "job_id": "j2",
        },
        {
            "title": "Data Scientist",
            "company": "Gamma",
            "jd_summary": "NLP and experiment tracking",
            "job_id": "j3",
        },
        {
            "title": "Platform Engineer",
            "company": "Delta",
            "jd_summary": "Infrastructure and automation",
            "job_id": "j4",
        },
    ]


def test_scores_between_zero_and_one():
    jobs = _sample_jobs()
    resume_embedding = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    model = MockSentenceTransformer(
        vectors=[
            [1.0, 0.0, 0.0],
            [0.7, 0.7, 0.0],
            [0.0, 1.0, 0.0],
            [-1.0, 0.0, 0.0],
        ]
    )

    ranked = rank_jobs(jobs, resume_embedding, model)

    for job in ranked:
        score = float(job["relevance_score"])
        assert 0.0 <= score <= 1.0


def test_sorted_descending():
    jobs = _sample_jobs()
    resume_embedding = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    model = MockSentenceTransformer(
        vectors=[
            [0.2, 1.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, 0.5, 0.0],
            [0.0, 1.0, 0.0],
        ]
    )

    ranked = rank_jobs(jobs, resume_embedding, model)
    scores = [job["relevance_score"] for job in ranked]

    assert scores == sorted(scores, reverse=True)


def test_top_n_respects_limit():
    jobs = _sample_jobs()
    top3 = select_top_n(jobs, n=3)
    assert len(top3) == 3


def test_top_n_handles_smaller_list():
    jobs = _sample_jobs()[:4]
    top25 = select_top_n(jobs, n=25)
    assert len(top25) == 4


def test_resume_text_construction():
    jobs = _sample_jobs()
    resume_embedding = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    model = MockSentenceTransformer(
        vectors=[
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
        ]
    )

    rank_jobs(jobs, resume_embedding, model)

    assert isinstance(model.last_inputs, list)
    assert model.last_inputs[0] == "ML Engineer Acme Graph models and fraud detection"

    expected_resume = (
        "Built temporal GNN TRDGNN achieving 0.58 PR-AUC on 203K-node fraud detection graph PyTorch Geometric XGBoost. "
        "PDF-to-JSON pipeline 100% JSON validity 81% evidence precision LLMs Pydantic Gemma DeepSeek Python Streamlit. "
        "10x GNN parameter reduction 500K to 50K with 108% performance gain resource-constrained systems. "
        "Python PyTorch PyG TensorFlow scikit-learn Docker Git Linux Streamlit Pydantic NumPy Pandas. "
        "CS undergrad IIIT Kota GNNs unstructured data pipelines production ML full test coverage reproducible research."
    )
    assert DEFAULT_RESUME_TEXT == expected_resume
