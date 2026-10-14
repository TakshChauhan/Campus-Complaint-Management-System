import re
import logging
from typing import Dict, List, Optional, Set
from sqlalchemy.orm import Session
from app.models.department import Department
from app.schemas.department import DepartmentSuggestionItem, DepartmentSuggestionResponse

logger = logging.getLogger("ccms.suggestion_service")

ADVISORY_DISCLAIMER = (
    "Automated keyword suggestions are strictly advisory. "
    "The complainant retains final authority to select their preferred department."
)

class SuggestionService:
    VERSION = "v1.2.0-keyword"

    def __init__(self, db: Session):
        self.db = db

    def suggest_departments(self, title: str, description: str) -> DepartmentSuggestionResponse:
        """Entry point for automated keyword-based advisory suggestion."""
        try:
            return self._heuristic_suggest(title, description)
        except Exception:
            logger.exception("Unexpected error in keyword suggestion service")
            return DepartmentSuggestionResponse(
                status="error_fallback",
                version=self.VERSION,
                suggestions=[],
                disclaimer=ADVISORY_DISCLAIMER,
            )

    def _normalize_text(self, text: str) -> tuple[str, Set[str]]:
        """Normalize text, handling wi-fi hyphenation and domain phrases."""
        lowered = text.lower()

        # Normalize wi-fi variants to unified 'wifi' token
        norm = re.sub(r'\bwi[\s\-_]+fi\b', 'wifi', lowered)

        # Normalize air conditioning variants
        norm = re.sub(r'\bair[\s\-_]+conditioning\b', 'air_conditioning', norm)
        norm = re.sub(r'\bair[\s\-_]+conditioner\b', 'air_conditioning', norm)
        norm = re.sub(r'\breading[\s\-_]+hall\b', 'reading_hall', norm)
        norm = re.sub(r'\breading[\s\-_]+room\b', 'reading_room', norm)

        # Tokenize whole words (avoiding partial substring matches)
        words = set(re.findall(r'\b[a-z0-9_]+\b', norm))
        return norm, words

    def _heuristic_suggest(self, title: str, description: str) -> DepartmentSuggestionResponse:
        # Retrieve only currently active departments
        departments = (
            self.db.query(Department)
            .filter(Department.is_active.is_(True))
            .all()
        )

        raw_text = f"{title} {description}"
        norm_text, words = self._normalize_text(raw_text)

        # Base keyword catalog grounded in verified DAU resolver department taxonomy
        keywords: Dict[str, Set[str]] = {
            "hostel": {"hostel", "room", "bed", "washroom", "bathroom", "tap", "fan", "water", "plumbing", "geyser"},
            "it services": {"wifi", "internet", "network", "portal", "login", "server", "lan", "ethernet", "router"},
            "library": {"book", "library", "journal", "catalog", "reading", "borrow", "reading_room", "reading_hall", "study"},
            "mess & cafeteria": {"mess", "food", "dining", "canteen", "meal", "breakfast", "lunch", "dinner", "cafeteria"},
            "sports & gymnasium": {"gym", "sports", "ground", "court", "badminton", "cricket", "football", "gymnasium"},
            "campus security": {"security", "guard", "gate", "patrol", "surveillance", "parking", "theft", "safety", "id_card"},
            "medical facility": {"doctor", "clinic", "medicine", "first_aid", "fever", "health", "hospital", "medical", "ambulance"},
        }

        # Detect domain context conflict:
        # Per seed description, Library specifically manages reading room facilities and air conditioning.
        # When library location context is explicit along with cooling issues, route to Library.
        library_context = {"library", "reading_room", "reading_hall"}.intersection(words)
        ac_context = {"ac", "air_conditioning"}.intersection(words)

        suggestions: List[DepartmentSuggestionItem] = []

        for dept in departments:
            dept_key = dept.name.lower()
            dept_keywords = keywords.get(dept_key, set())

            # Find matching terms
            matched = set(dept_keywords.intersection(words))

            # Contextual resolution for Library AC:
            if dept_key == "library" and library_context and ac_context:
                matched.update(ac_context)

            if matched:
                # Base 0.60 + 0.10 per keyword, bounded at 0.95
                confidence = min(0.95, 0.60 + 0.10 * len(matched))
                # Deterministic rationale with sorted keyword strings
                formatted_keywords = [k.replace("_", " ") for k in sorted(matched)]
                rationale_str = f"Matched keywords relating to {dept.name}: {', '.join(formatted_keywords)}"

                suggestions.append(
                    DepartmentSuggestionItem(
                        department_id=dept.id,
                        department_name=dept.name,
                        confidence_score=round(confidence, 2),
                        rationale=rationale_str,
                    )
                )

        # Deterministic sort: confidence desc, then department name asc
        suggestions.sort(key=lambda item: (-item.confidence_score, item.department_name))

        # Case 1: No matches -> uncertain with empty suggestions
        if not suggestions:
            return DepartmentSuggestionResponse(
                status="uncertain",
                version=self.VERSION,
                suggestions=[],
                disclaimer=ADVISORY_DISCLAIMER,
            )

        # Case 2: Tied top score -> uncertain with the tied candidate list
        if len(suggestions) >= 2 and suggestions[0].confidence_score == suggestions[1].confidence_score:
            top_score = suggestions[0].confidence_score
            tied_candidates = [s for s in suggestions if s.confidence_score == top_score]
            return DepartmentSuggestionResponse(
                status="uncertain",
                version=self.VERSION,
                suggestions=tied_candidates,
                disclaimer=ADVISORY_DISCLAIMER,
            )

        # Case 3: Clear candidate winner -> provisional_advisory
        return DepartmentSuggestionResponse(
            status="provisional_advisory",
            version=self.VERSION,
            suggestions=suggestions,
            disclaimer=ADVISORY_DISCLAIMER,
        )
