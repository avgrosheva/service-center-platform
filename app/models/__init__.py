"""
Import every model module here so Base.metadata is fully populated for
anything that inspects it (Alembic autogenerate, tests, etc.), and so
other code can do `from app.models import Organization` instead of
reaching into the submodule directly.
"""

from app.models.organization import Organization  # noqa: F401
from app.models.user import User, UserRole  # noqa: F401
from app.models.customer import Customer  # noqa: F401
from app.models.equipment import Equipment  # noqa: F401
from app.models.job import Job, JobStatus  # noqa: F401
from app.models.job_status_history import JobEventType, JobStatusHistory  # noqa: F401
from app.models.photo import Photo, PhotoTag  # noqa: F401
from app.models.material_item import MaterialItem  # noqa: F401
from app.models.additional_work_item import AdditionalWorkItem, AdditionalWorkStatus  # noqa: F401
from app.models.payment import Payment, PaymentMethod, PaymentStatus  # noqa: F401
from app.models.document import Document, DocumentType  # noqa: F401
from app.models.ai_task import AITask, AITaskStatus, AITaskType  # noqa: F401