from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.department import Department


def get_active_departments(db: Session) -> List[Department]:
    """Retrieve all active departments in deterministic alphabetical order."""
    return (
        db.query(Department)
        .filter(Department.is_active.is_(True))
        .order_by(Department.name.asc())
        .all()
    )


def get_department_by_id(db: Session, department_id: int) -> Optional[Department]:
    """Lookup a single department by its primary key."""
    return db.query(Department).filter(Department.id == department_id).first()
