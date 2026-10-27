# Import all the models, so that Base has them registered
# before being imported by Alembic or database initialization scripts
from app.db.base_class import Base  # noqa: F401
from app.models.department import Department  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.complaint import Complaint  # noqa: F401
from app.models.complaint_status_history import ComplaintStatusHistory  # noqa: F401
from app.models.hostel import Hostel  # noqa: F401
from app.models.hostel_wing import HostelWing  # noqa: F401
from app.models.hostel_floor import HostelFloor  # noqa: F401
from app.models.student_residence import StudentResidence  # noqa: F401
from app.models.oauth import UserExternalIdentity, OAuthTransaction, OAuthHandoffTicket  # noqa: F401
