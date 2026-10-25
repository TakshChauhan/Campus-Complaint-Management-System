"""Privacy-scoped TF-IDF duplicate complaint suggestions."""

import math
import re
from collections import Counter
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.complaint import Complaint
from app.models.user import User


# Provisional threshold: requires evaluation on labelled pairs.
DEFAULT_THRESHOLD = 0.15


def tokenize(text: str) -> list[str]:
    return re.findall(r"(?u)\b\w\w+\b", text.lower())


def tfidf_vectors(texts: list[str]) -> list[dict[str, float]]:
    """Compute normalized TF-IDF vectors using smoothed IDF."""
    token_lists = [tokenize(text) for text in texts]
    n = len(token_lists)

    document_frequency = Counter()
    for tokens in token_lists:
        document_frequency.update(set(tokens))

    vectors = []

    for tokens in token_lists:
        frequencies = Counter(tokens)
        vector = {}

        for word, frequency in frequencies.items():
            idf = math.log(
                (1 + n) / (1 + document_frequency[word])
            ) + 1

            vector[word] = frequency * idf

        norm = math.sqrt(sum(v * v for v in vector.values()))

        if norm:
            vector = {
                word: value / norm
                for word, value in vector.items()
            }

        vectors.append(vector)

    return vectors


def cosine_similarity(
    first: dict[str, float],
    second: dict[str, float],
) -> float:
    return sum(
        value * second.get(word, 0.0)
        for word, value in first.items()
    )


def find_similar(
    db: Session,
    student: User,
    title: str,
    description: str,
    max_results: int = 3,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[dict[str, Any]]:
    """
    Return similar public complaints and the student's own complaints.

    Never include another student's private complaints in the
    similarity corpus, even temporarily.

    No creator identity fields are returned.
    """
    if student.role != "student":
        raise ValueError("Duplicate suggestions require a student")

    candidates = (
        db.query(Complaint)
        .options(joinedload(Complaint.department))
        .filter(
            or_(
                Complaint.is_public.is_(True),
                Complaint.created_by_id == student.id,
            )
        )
        .all()
    )

    if not candidates:
        return []

    query_text = f"{title} {description}"

    candidate_texts = [
        f"{complaint.title} {complaint.description}"
        for complaint in candidates
    ]

    vectors = tfidf_vectors([query_text, *candidate_texts])
    query_vector = vectors[0]

    matches = []

    for complaint, vector in zip(candidates, vectors[1:]):
        score = cosine_similarity(query_vector, vector)

        if score < threshold:
            continue

        matches.append({
            "id": complaint.id,
            "title": complaint.title,
            "department_id": complaint.department_id,
            "department_name": (
                complaint.department.name
                if complaint.department
                else "Unknown"
            ),
            "status": complaint.status,
            "similarity_score": round(score, 4),
        })

    matches.sort(
        key=lambda item: (
            -item["similarity_score"],
            -item["id"],
        )
    )

    return matches[:max_results]
