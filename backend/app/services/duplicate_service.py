"""Privacy-scoped TF-IDF duplicate suggestions for only complaints the student may see."""
import math
import re
from collections import Counter
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.complaint import Complaint
from app.models.department import Department
from app.models.hmc_group import HMCGroupWing
from app.models.user import User
from app.services.public_feed_service import (
    PUBLICATION_PUBLISHED,
    REVIEW_APPROVED,
    REVIEW_AUTO_APPROVED,
    SCOPE_DEPARTMENT_PUBLIC,
    SCOPE_HMC_GROUP_PUBLIC,
    _student_hmc_group,
)

DEFAULT_THRESHOLD = 0.15


def tokenize(text: str) -> list[str]:
    return re.findall(r"(?u)\b\w\w+\b", text.lower())


def tfidf_vectors(texts: list[str]) -> list[dict[str, float]]:
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
            idf = math.log((1 + n) / (1 + document_frequency[word])) + 1
            vector[word] = frequency * idf
        norm = math.sqrt(sum(v * v for v in vector.values()))
        if norm:
            vector = {word: value / norm for word, value in vector.items()}
        vectors.append(vector)
    return vectors


def cosine_similarity(first: dict[str, float], second: dict[str, float]) -> float:
    return sum(value * second.get(word, 0.0) for word, value in first.items())


def _visible_public_candidates(db: Session, student: User) -> list[Complaint]:
    """Load only published public complaints which this student can access, plus their own records."""
    own = db.query(Complaint).options(joinedload(Complaint.department)).filter(
        Complaint.created_by_id == student.id
    ).all()
    visible: dict[int, Complaint] = {item.id: item for item in own}
    public_department = db.query(Complaint).options(joinedload(Complaint.department)).join(
        Department, Department.id == Complaint.department_id
    ).filter(
        Department.is_active.is_(True), Complaint.is_public.is_(True),
        Complaint.publication_status == PUBLICATION_PUBLISHED,
        Complaint.visibility_scope == SCOPE_DEPARTMENT_PUBLIC,
        Complaint.affected_building_id.is_(None), Complaint.affected_floor_id.is_(None),
        Complaint.affected_wing_id.is_(None),
    ).all()
    visible.update({item.id: item for item in public_department})

    # HMC candidates are permitted only when this student's verified residence maps to a valid group.
    try:
        group = _student_hmc_group(db, student)
    except HTTPException:
        group = None
    if group is not None:
        wing_ids = [row.wing_id for row in db.query(HMCGroupWing).filter(
            HMCGroupWing.hmc_group_id == group.id,
            HMCGroupWing.building_id == group.building_id,
            HMCGroupWing.floor_id == group.floor_id,
        ).all()]
        if wing_ids:
            hmc = db.query(Complaint).options(joinedload(Complaint.department)).join(
                Department, Department.id == Complaint.department_id
            ).filter(
                Department.is_active.is_(True), Complaint.is_public.is_(True),
                Complaint.publication_status == PUBLICATION_PUBLISHED,
                Complaint.visibility_scope == SCOPE_HMC_GROUP_PUBLIC,
                Complaint.feed_review_status.in_([REVIEW_APPROVED, REVIEW_AUTO_APPROVED]),
                Complaint.affected_building_id == group.building_id,
                Complaint.affected_floor_id == group.floor_id,
                or_(Complaint.affected_wing_id.is_(None), Complaint.affected_wing_id.in_(wing_ids)),
            ).all()
            visible.update({item.id: item for item in hmc})
    return list(visible.values())


def find_similar(db: Session, student: User, title: str, description: str,
                 max_results: int = 3, threshold: float = DEFAULT_THRESHOLD) -> list[dict[str, Any]]:
    """Return suggestions from the student's own records and public summaries they can access.

    Complaint descriptions are read only inside this backend comparison. They are never included in the
    returned suggestion objects. Pending/rejected/private complaints by other students and HMC complaints
    from other groups are excluded before building the similarity corpus.
    """
    if student.role != "student":
        raise ValueError("Duplicate suggestions require a student")
    candidates = _visible_public_candidates(db, student)
    if not candidates:
        return []
    query_text = f"{title} {description}"
    candidate_texts = [f"{complaint.title} {complaint.description}" for complaint in candidates]
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
            "department_name": complaint.department.name if complaint.department else "Unknown",
            "status": complaint.status,
            "similarity_score": round(score, 4),
        })
    matches.sort(key=lambda item: (-item["similarity_score"], -item["id"]))
    return matches[:max_results]
