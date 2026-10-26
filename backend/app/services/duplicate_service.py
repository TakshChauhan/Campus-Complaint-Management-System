import logging
from typing import List, Dict, Any, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger("ccms.duplicate_service")

# Threshold picked from Yash's labelled pairs benchmark
PRODUCTION_THRESHOLD = 0.70


def find_similar(
    title: str,
    description: str,
    candidate_complaints: List[Dict[str, Any]],
    current_student_id: Optional[int] = None,
    threshold: float = PRODUCTION_THRESHOLD
) -> List[Dict[str, Any]]:
    """
    Finds top 3 similar complaints using TF-IDF and Cosine Similarity.
    
    Acceptance Criteria:
    - Compares only against public complaints and the student's own.
    - Returns title, department, status, and score (never creator info).
    - If service fails, returns [] so complaint submission is never blocked.
    """
    try:
        query_text = f"{title or ''} {description or ''}".strip()
        if not query_text or not candidate_complaints:
            return []

        # 1. Eligibility Filter: Only public OR owned by current student
        eligible_candidates = [
            c for c in candidate_complaints
            if c.get("is_public") is True or (
                current_student_id is not None and c.get("user_id") == current_student_id
            )
        ]

        if not eligible_candidates:
            return []

        # 2. Build text corpus
        candidate_texts = [
            f"{c.get('title', '')} {c.get('description', '')}".strip()
            for c in eligible_candidates
        ]
        corpus = [query_text] + candidate_texts

        # 3. TF-IDF & Cosine Similarity
        vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
            sublinear_tf=True
        )
        tfidf_matrix = vectorizer.fit_transform(corpus)
        sim_scores = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]

        # 4. Filter matches above threshold (Redacting PII / creator info)
        matches = []
        for idx, score in enumerate(sim_scores):
            if score >= threshold:
                c = eligible_candidates[idx]
                matches.append({
                    "title": c.get("title", ""),
                    "department": c.get("department", ""),
                    "status": c.get("status", ""),
                    "score": round(float(score), 3)
                })

        # Top 3 matches sorted descending
        matches.sort(key=lambda x: x["score"], reverse=True)
        return matches[:3]

    except Exception:
        logger.exception("Duplicate suggestion service error; returning empty fallback")
        return []

DEFAULT_THRESHOLD = PRODUCTION_THRESHOLD

