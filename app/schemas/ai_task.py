"""
Pydantic v2 schemas for AITask and the /ai/* request bodies (Milestone 18).

Every free-text input field carries a max_length — "reasonable input size
limits on voice notes / free-text queries to avoid runaway API costs" per
the roadmap's own validation rules. The limits below are deliberately
generous (a technician's rambling voice note, a detailed question) while
still ruling out someone pasting an entire novel into the request body.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.ai_task import AITaskStatus, AITaskType

_MAX_TRANSCRIPT_LENGTH = 20_000
_MAX_QUERY_LENGTH = 2_000


class VoiceNoteRequest(BaseModel):
    # See workers/ai_tasks.py's module docstring for why this takes an
    # already-transcribed string rather than an audio file/S3 key: the
    # Claude Messages API has no audio input content block, so actual
    # speech-to-text is out of this milestone's scope — this endpoint's
    # AI value-add is structuring a raw transcript into a clean technician
    # note, not producing the transcript itself.
    transcript: str = Field(min_length=1, max_length=_MAX_TRANSCRIPT_LENGTH)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=_MAX_QUERY_LENGTH)


class AITaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    job_id: uuid.UUID | None
    task_type: AITaskType
    status: AITaskStatus
    input_ref: str
    output: str | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None
