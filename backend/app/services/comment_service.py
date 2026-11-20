"""Complaint comments (S5-05).

Access is decided by the same loaders the complaint detail routes use, so a
comment route can never see more than its detail route:

* owner routes  -> ``complaint_service.load_owned_complaint``
* staff routes  -> ``staff_service.load_department_complaint`` (department +
  S4-04 hostel scope)

A complaint that does not exist and one the caller may not see both give 404.
Comments are append-only (no edit or delete) and are allowed in every status.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models.complaint_comment import ComplaintComment
from app.models.user import User
from app.schemas.comment import CommentOut
from app.services.complaint_service import load_owned_complaint
from app.services.staff_service import load_department_complaint


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found.")


def _load_for_owner(db: Session, user: User, complaint_id: int) -> int:
    if user.role != "student":
        raise _not_found()
    return load_owned_complaint(db, user.id, complaint_id).id


def _load_for_staff(db: Session, user: User, complaint_id: int) -> int:
    # Any signed-in user outside the handling staff gets 404, including staff
    # with no department (the detail route answers 403 there; for comments
    # the contract asks for one uniform "not found").
    if user.role != "staff" or user.department_id is None:
        raise _not_found()
    return load_department_complaint(db, user, complaint_id).id


def _to_out(comment: ComplaintComment, viewer: User) -> CommentOut:
    author = comment.author
    return CommentOut(
        id=comment.id,
        body=comment.body,
        created_at=comment.created_at,
        author_role=author.role,
        author_name=author.name,
        is_mine=comment.author_id == viewer.id,
    )


def _list(
    db: Session, viewer: User, complaint_id: int, *, limit: int, offset: int
) -> tuple[list[CommentOut], int]:
    query = db.query(ComplaintComment).filter(ComplaintComment.complaint_id == complaint_id)
    total = query.count()
    comments = (
        query.options(joinedload(ComplaintComment.author))
        .order_by(ComplaintComment.created_at.asc(), ComplaintComment.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_to_out(comment, viewer) for comment in comments], total


def _create(db: Session, author: User, complaint_id: int, body: str) -> CommentOut:
    comment = ComplaintComment(complaint_id=complaint_id, author_id=author.id, body=body)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return _to_out(comment, author)


def list_owner_comments(
    db: Session, student: User, complaint_id: int, *, limit: int, offset: int
) -> tuple[list[CommentOut], int]:
    complaint_id = _load_for_owner(db, student, complaint_id)
    return _list(db, student, complaint_id, limit=limit, offset=offset)


def add_owner_comment(db: Session, student: User, complaint_id: int, body: str) -> CommentOut:
    complaint_id = _load_for_owner(db, student, complaint_id)
    return _create(db, student, complaint_id, body)


def list_staff_comments(
    db: Session, staff: User, complaint_id: int, *, limit: int, offset: int
) -> tuple[list[CommentOut], int]:
    complaint_id = _load_for_staff(db, staff, complaint_id)
    return _list(db, staff, complaint_id, limit=limit, offset=offset)


def add_staff_comment(db: Session, staff: User, complaint_id: int, body: str) -> CommentOut:
    complaint_id = _load_for_staff(db, staff, complaint_id)
    return _create(db, staff, complaint_id, body)
