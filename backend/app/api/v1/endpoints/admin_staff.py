
"""Administrator-only staff hostel assignment endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_admin
from app.models.hostel import Hostel
from app.models.staff_hostel_assignment import StaffHostelAssignment
from app.models.user import User
from app.repositories.staff_hostel_assignment_repository import (
    get_hostels_for_staff,
)
from app.schemas.admin_staff import (
    AdminStaffHostel,
    AdminStaffListItem,
    StaffHostelAssignmentUpdate,
)

router = APIRouter(prefix="/admin/staff", tags=["Admin Staff"])


@router.get(
    "",
    response_model=List[AdminStaffListItem],
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Missing or invalid authentication token"},
        403: {"description": "Administrator role required"},
    },
)
def list_admin_staff(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """List staff members with their departments and assigned hostels."""

    staff_members = (
        db.query(User)
        .filter(User.role == "staff")
        .order_by(User.id)
        .all()
    )

    result = []

    for staff in staff_members:
        assigned_hostels = get_hostels_for_staff(db, staff.id)

        result.append(
            AdminStaffListItem(
                id=staff.id,
                name=staff.name,
                email=staff.email,
                department_id=staff.department_id,
                department_name=(
                    staff.department.name if staff.department else None
                ),
                hostels=[
                    AdminStaffHostel(
                        id=hostel.id,
                        code=hostel.code,
                        name=hostel.name,
                    )
                    for hostel in assigned_hostels
                ],
            )
        )

    return result


@router.put(
    "/{staff_id}/hostels",
    response_model=AdminStaffListItem,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Missing or invalid authentication token"},
        403: {"description": "Administrator role required"},
        422: {"description": "Invalid staff member or hostel ID"},
    },
)
def replace_staff_hostel_assignments(
    staff_id: int,
    payload: StaffHostelAssignmentUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Replace all hostel assignments for a staff member."""

    # Verify that the target user exists and is a staff member.
    staff = (
        db.query(User)
        .filter(User.id == staff_id)
        .first()
    )

    if staff is None or staff.role != "staff":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="User does not exist or is not a staff member",
        )

    # Remove duplicate IDs while preserving their original order.
    hostel_ids = list(dict.fromkeys(payload.hostel_ids))

    # Validate every requested hostel before changing existing assignments.
    hostels = []

    if hostel_ids:
        hostels = (
            db.query(Hostel)
            .filter(Hostel.id.in_(hostel_ids))
            .order_by(Hostel.id)
            .all()
        )

        found_ids = {hostel.id for hostel in hostels}
        invalid_ids = [
            hostel_id
            for hostel_id in hostel_ids
            if hostel_id not in found_ids
        ]

        if invalid_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid hostel IDs: {invalid_ids}",
            )

    try:
        # Delete the previous assignments.
        (
            db.query(StaffHostelAssignment)
            .filter(StaffHostelAssignment.user_id == staff_id)
            .delete(synchronize_session=False)
        )

        # Insert the complete new assignment set.
        new_assignments = [
            StaffHostelAssignment(
                user_id=staff_id,
                hostel_id=hostel_id,
                assigned_by_id=admin.id,
            )
            for hostel_id in hostel_ids
        ]

        db.add_all(new_assignments)
        db.commit()

    except Exception:
        db.rollback()
        raise

    # Return the updated staff member and their assignments.
    assigned_hostels = get_hostels_for_staff(db, staff.id)

    return AdminStaffListItem(
        id=staff.id,
        name=staff.name,
        email=staff.email,
        department_id=staff.department_id,
        department_name=(
            staff.department.name if staff.department else None
        ),
        hostels=[
            AdminStaffHostel(
                id=hostel.id,
                code=hostel.code,
                name=hostel.name,
            )
            for hostel in assigned_hostels
        ],
    )
