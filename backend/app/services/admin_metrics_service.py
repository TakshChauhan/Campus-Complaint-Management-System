"""Read-only aggregation services for the administrator metrics dashboard."""

from typing import Any, Dict

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.complaint import Complaint
from app.models.department import Department
from app.services.complaint_lifecycle_service import calculate_rolling_resolution_metrics


COMPLAINT_LIFECYCLE_STATUSES = ("submitted", "in_progress", "resolved", "reopened")
DEFAULT_ADMIN_METRICS_WINDOW_DAYS = 30


def get_admin_metrics_summary(db: Session) -> Dict[str, Any]:
    """Build the dashboard summary from all complaints and active departments.

    Total and lifecycle-status counts include every complaint record, regardless
    of feed publication visibility or whether its department is currently active.
    Department rows are limited to active departments and include departments
    with no complaints. Resolution statistics reuse the canonical lifecycle
    calculation so both admin endpoints report identical metric semantics.
    """
    grouped_status_counts = (
        db.query(Complaint.status, func.count(Complaint.id))
        .group_by(Complaint.status)
        .all()
    )
    counts_by_status = {status: count for status, count in grouped_status_counts}

    status_counts = [
        {"status": status, "count": int(counts_by_status.get(status, 0))}
        for status in COMPLAINT_LIFECYCLE_STATUSES
    ]
    total_complaints = int(sum(counts_by_status.values()))

    department_rows = (
        db.query(
            Department.id,
            Department.name,
            func.count(Complaint.id).label("complaint_count"),
        )
        .outerjoin(Complaint, Complaint.department_id == Department.id)
        .filter(Department.is_active.is_(True))
        .group_by(Department.id, Department.name)
        .order_by(Department.name.asc(), Department.id.asc())
        .all()
    )
    department_counts = [
        {
            "department_id": department_id,
            "department_name": department_name,
            "count": int(complaint_count),
        }
        for department_id, department_name, complaint_count in department_rows
    ]

    resolution_metrics = calculate_rolling_resolution_metrics(
        db,
        window_days=DEFAULT_ADMIN_METRICS_WINDOW_DAYS,
    )

    return {
        "total_complaints": total_complaints,
        "status_counts": status_counts,
        "department_counts": department_counts,
        "resolution_metrics": resolution_metrics,
    }
