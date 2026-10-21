"""Response schema for complaint status-history events."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ComplaintStatusHistoryItem(BaseModel):
    """One status event without actor names, emails, or credentials."""

    id: int
    from_status: str | None = None
    to_status: str
    actor_id: int
    remark: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
