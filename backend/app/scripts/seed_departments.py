"""
Idempotent Department Seed Script for CCMS

NOTE: The departments listed here are PROVISIONAL campus departments
(e.g., Hostel, IT Services, Library, Mess, Sports, Estate & Facility).
The official university department taxonomy must be formally confirmed
by institutional stakeholders before production deployment.

Frontend and client integrations MUST dynamically fetch department IDs from
GET /api/v1/departments rather than hardcoding numeric IDs in frontend code.
"""

import sys
import logging
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, engine
from app.models.department import Department
from app.db.base_class import Base

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ccms.seed_departments")

# Official DA-IICT / DAU resolver department catalog
PROVISIONAL_DEPARTMENTS = [
    {
        "name": "Hostel",
        "description": "Halls of Residence room maintenance, electrical, plumbing, furniture, and living conditions.",
        "is_active": True,
    },
    {
        "name": "IT Services",
        "description": "Campus Wi-Fi, 1Gbps LAN, student portal, HPC cluster, lab machines, and data center support.",
        "is_active": True,
    },
    {
        "name": "Library",
        "description": "Resource Centre (RC) books, digital archives, OPAC search, air conditioning, and reading halls.",
        "is_active": True,
    },
    {
        "name": "Mess & Cafeteria",
        "description": "Food court, canteens, dining hygiene, meal quality, and campus cafeteria services.",
        "is_active": True,
    },
    {
        "name": "Sports & Gymnasium",
        "description": "Sports complex, athletic track, cricket field, badminton/basketball courts, and gymnasium.",
        "is_active": True,
    },
    {
        "name": "Campus Security",
        "description": "24x7 security personnel, entry/exit gates, vehicle parking, CCTV surveillance, and campus safety.",
        "is_active": True,
    },
    {
        "name": "Medical Facility",
        "description": "On-campus Medical Centre, visiting doctor consultations, first aid, medicines, and emergency vehicle.",
        "is_active": True,
    },
]


def seed_departments(db: Session) -> None:
    """Idempotently seed provisional campus departments without duplicates."""
    logger.info("Starting idempotent department seeding...")
    created_count = 0
    updated_count = 0

    for item in PROVISIONAL_DEPARTMENTS:
        dept = db.query(Department).filter(Department.name == item["name"]).first()
        if dept is None:
            dept = Department(
                name=item["name"],
                description=item["description"],
                is_active=item["is_active"],
            )
            db.add(dept)
            created_count += 1
            logger.info("Created provisional department: '%s'", item["name"])
        else:
            # Keep description up to date if modified
            dept.description = item["description"]
            # Do NOT override is_active if it was deactivated manually
            updated_count += 1
            logger.info("Existing department '%s' refreshed (is_active=%s)", item["name"], dept.is_active)

    db.commit()
    logger.info(
        "Seeding complete! Added: %d, Updated: %d, Total Active: %d",
        created_count,
        updated_count,
        db.query(Department).filter(Department.is_active.is_(True)).count(),
    )



if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_departments(db)
    except Exception as e:
        logger.error("Error during department seeding: %s", str(e))
        db.rollback()
        sys.exit(1)
    finally:
        db.close()
