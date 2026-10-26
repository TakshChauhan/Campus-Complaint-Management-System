
import logging
from typing import Any, Dict, List, Optional, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger("ccms.backend")

PRODUCTION_THRESHOLD = 0.70
DEFAULT_THRESHOLD = PRODUCTION_THRESHOLD


def _get_value(item: Any, key: str, default: Any = None) -> Any:
    """Read a field from a dictionary or ORM object."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _department_details(complaint: Any) -> Tuple[int, str]:
    """Extract department ID and name."""
    department = _get_value(complaint, "department")
    department_id = _get_value(complaint, "department_id", 0)
    department_name = _get_value(complaint, "department_name", "")

    if isinstance(department, dict):
        department_id = department.get("id", department_id)
        department_name = department.get("name", department_name)
    elif isinstance(department, str):
        department_name = department_name or department
    elif department is not None:
        department_id = getattr(department, "id", department_id)
        department_name = getattr(
            department, "name", department_name
        )

    try:
        department_id = int(department_id or 0)
    except (TypeError, ValueError):
        department_id = 0

    return department_id, str(department_name or "")


def _accessible_candidates(
    candidates: List[Any],
    current_student_id: Optional[int],
) -> List[Any]:
    """Exclude private complaints belonging to other students."""
    accessible = []

    for candidate in candidates:
        is_public = bool(_get_value(candidate, "is_public", False))

        creator_id = _get_value(candidate, "created_by_id")
        if creator_id is None:
            creator_id = _get_value(candidate, "user_id")

        # When no student ID is supplied, rely on the caller's
        # access-controlled candidate query.
        if current_student_id is None:
            accessible.append(candidate)
            continue

        if is_public or (
            creator_id is not None
            and str(creator_id) == str(current_student_id)
        ):
            accessible.append(candidate)

    return accessible


def find_similar(
    title: str,
    description: str,
    candidates: Optional[List[Any]] = None,
    threshold: float = PRODUCTION_THRESHOLD,
    top_k: int = 3,
    *,
    db: Any = None,
    student: Any = None,
    candidate_complaints: Optional[List[Any]] = None,
    current_student_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Find similar complaints using TF-IDF and cosine similarity.

    Supports both:
      find_similar(title, description, candidates=[...])
      find_similar(title, description, candidate_complaints=[...],
                   current_student_id=...)

    It also supports the db/student calling style used by the API.
    Creator IDs and other identifying information are never returned.
    """
    try:
        if candidate_complaints is not None:
            candidates = candidate_complaints

        if student is not None:
            current_student_id = _get_value(student, "id")

        # Support the API calling style: find_similar(db=..., student=...).
        if candidates is None and db is not None:
            from sqlalchemy import or_
            from app.models.complaint import Complaint

            query = db.query(Complaint)

            if current_student_id is not None:
                query = query.filter(
                    or_(
                        Complaint.is_public.is_(True),
                        Complaint.created_by_id == current_student_id,
                    )
                )
            else:
                query = query.filter(Complaint.is_public.is_(True))

            candidates = query.all()

        candidates = candidates or []

        if not title and not description:
            return []

        candidates = _accessible_candidates(
            candidates, current_student_id
        )

        if not candidates:
            return []

        query_text = f"{title or ''} {description or ''}".strip()
        if not query_text:
            return []

        candidate_texts: List[str] = []
        valid_candidates: List[Any] = []

        for candidate in candidates:
            candidate_title = _get_value(
                candidate, "title", ""
            ) or ""
            candidate_description = _get_value(
                candidate, "description", ""
            ) or ""

            text = f"{candidate_title} {candidate_description}".strip()

            if text:
                candidate_texts.append(text)
                valid_candidates.append(candidate)

        if not candidate_texts:
            return []

        vectorizer = TfidfVectorizer(stop_words="english")
        matrix = vectorizer.fit_transform(
            [query_text] + candidate_texts
        )

        similarities = cosine_similarity(
            matrix[0:1], matrix[1:]
        )[0]

        matches: List[Dict[str, Any]] = []

        for index, similarity in enumerate(similarities):
            score = float(similarity)

            if score < threshold:
                continue

            candidate = valid_candidates[index]
            complaint_id = _get_value(candidate, "id")
            complaint_title = _get_value(
                candidate, "title", ""
            ) or ""

            try:
                complaint_id = int(complaint_id)
            except (TypeError, ValueError):
                logger.warning("Skipping complaint with invalid ID")
                continue

            department_id, department_name = _department_details(
                candidate
            )

            department = _get_value(candidate, "department")
            if isinstance(department, dict):
                department_value = department.get(
                    "name", department_name
                )
            elif isinstance(department, str):
                department_value = department
            else:
                department_value = department_name

            complaint_status = _get_value(
                candidate, "status", ""
            )
            if hasattr(complaint_status, "value"):
                status_value = str(complaint_status.value)
            else:
                status_value = str(complaint_status or "")

            matches.append(
                {
                    "id": complaint_id,
                    "title": str(complaint_title),
                    "department_id": department_id,
                    "department_name": department_name,
                    "department": str(department_value or ""),
                    "status": status_value,
                    "similarity_score": round(score, 4),
                }
            )

        matches.sort(
            key=lambda item: item["similarity_score"],
            reverse=True,
        )

        return matches[:max(0, top_k)]

    except Exception:
        logger.exception(
            "Duplicate suggestions failed; returning empty results"
        )
        return []
