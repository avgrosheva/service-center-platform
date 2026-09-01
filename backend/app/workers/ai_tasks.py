"""
AI task execution (Milestone 18) — the actual Anthropic API call and
result write-back, invoked via FastAPI `BackgroundTasks` per the frozen
async-only rule for AI ("Processing model — always asynchronous").

Follows document_tasks.py's shape: opens its own DB session (never reuses
the request-scoped one — see that module's docstring for why), takes only
a plain task_id as its argument, and is scheduled from the router after
ai_service.py has already validated access and committed a `pending` row
synchronously within the request.

Differs from document_tasks.py in one structural way: a Document's mere
existence *is* its status signal, so a failed document generation simply
rolls back and leaves no row. An AITask's row already exists (in
`pending`) before this function ever runs — the whole polling contract
(`GET /ai/tasks/{id}`) depends on that row being visible immediately. So
failure here is a separate, always-attempted final write (`status=failed`,
`error=...`), not a rollback-and-disappear — the row must end in an
observable terminal state (`done` or `failed`), never stuck in `pending`
or `processing` forever with no trace, matching Milestone 17's "no
background task silently fails without some observable trace" bar,
applied to this task's own status field rather than only the logs.

**On voice-note "transcription":** the Claude Messages API has no audio
input content block (only text, image, PDF, and files-API references to
those) — there is no documented way to hand raw audio to `messages.create`
for transcription. Building this endpoint to actually transcribe audio
would mean inventing an API surface Claude doesn't have. So
`VoiceNoteRequest.transcript` (see schemas/ai_task.py) takes an
already-transcribed string, and this task's only AI value-add for that
type is structuring a rough transcript into a clean, organized technician
note — not producing the transcript itself. That's a deliberate scope
decision, not a placeholder for a future audio branch.

The actual Anthropic call is isolated in `_call_claude` specifically so
tests can monkeypatch it — the same pattern Milestone 17's tests used for
`s3_client.upload_bytes` — avoiding real network calls/API costs in the
test suite while still exercising the full pending -> processing ->
done/failed lifecycle end to end.
"""

import logging
import uuid
from datetime import datetime, timezone

from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.ai_task import AITask, AITaskStatus, AITaskType
from app.models.customer import Customer
from app.models.job import Job
from app.models.job_status_history import JobStatusHistory

logger = logging.getLogger(__name__)

# Haiku 4.5, not a higher-tier model: this is an optional assist layer
# (structuring a rough transcript, a short summary, a bounded-context
# suggestion or Q&A answer) with no need for deep reasoning — exactly the
# "simple, speed-critical" workload profile the model is suited for, at
# roughly a fifth of Opus-tier cost. A deliberate choice given AI is the
# first thing the roadmap names as safe to cut/scale back if needed.
_MODEL = "claude-haiku-4-5"
_MAX_OUTPUT_TOKENS = 1024

# How many of the organization's most recent jobs get pulled into a
# /ai/query prompt as grounding context. Unbounded would let prompt size
# (and cost) grow with the organization's entire history; this keeps both
# bounded while still covering "recent activity" queries, which is what
# an owner actually asks about day to day.
_QA_CONTEXT_JOB_LIMIT = 50


async def process_ai_task(task_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        task = await db.get(AITask, task_id)
        if task is None:
            logger.error("AI task processing skipped: task %s not found", task_id)
            return
        task.status = AITaskStatus.PROCESSING
        await db.commit()

    try:
        output = await _run(task_id)
    except Exception as exc:
        logger.exception("AI task %s failed", task_id)
        async with AsyncSessionLocal() as db:
            task = await db.get(AITask, task_id)
            if task is not None:
                task.status = AITaskStatus.FAILED
                task.error = str(exc)
                task.completed_at = datetime.now(timezone.utc)
                await db.commit()
        return

    async with AsyncSessionLocal() as db:
        task = await db.get(AITask, task_id)
        if task is not None:
            task.status = AITaskStatus.DONE
            task.output = output
            task.completed_at = datetime.now(timezone.utc)
            await db.commit()


async def _run(task_id: uuid.UUID) -> str:
    async with AsyncSessionLocal() as db:
        task = await db.get(AITask, task_id)
        if task is None:
            raise RuntimeError(f"AI task {task_id} disappeared before processing")

        prompt = await _build_prompt(db, task)

    return await _call_claude(prompt)


async def _build_prompt(db: AsyncSession, task: AITask) -> str:
    if task.task_type == AITaskType.VOICE_TRANSCRIPTION:
        return (
            "You are cleaning up a field technician's raw voice-note transcript into a "
            "clear, organized note for a job record. Fix obvious transcription errors and "
            "filler words, but preserve every technical detail (parts, measurements, "
            "diagnoses). Return only the cleaned note text, no preamble.\n\n"
            f"Transcript:\n{task.input_ref}"
        )

    if task.task_type == AITaskType.SUMMARY:
        context = await _load_job_context(db, uuid.UUID(task.input_ref))
        return (
            "Write a short, plain-language, customer-friendly summary of the repair work "
            "described below, suitable for sending directly to the customer. Do not "
            "invent details not present in the data. Return only the summary text.\n\n"
            f"{context}"
        )

    if task.task_type == AITaskType.ADDITIONAL_WORK_SUGGESTION:
        context = await _load_job_context(db, uuid.UUID(task.input_ref))
        return (
            "Based on the technician's notes below, suggest any additional repair work "
            "that may be worth flagging for owner/dispatcher review. These are only "
            "suggestions for a human to evaluate — never state them as already approved "
            "or already billed. If nothing stands out, say so plainly. Return a short "
            "bulleted list or a single sentence if there's nothing to suggest.\n\n"
            f"{context}"
        )

    if task.task_type == AITaskType.QA_QUERY:
        context = await _load_org_query_context(db, task.organization_id)
        return (
            "Answer the following question using only the job history data provided "
            "below. If the data doesn't contain enough information to answer, say so "
            "plainly rather than guessing.\n\n"
            f"Job history:\n{context}\n\n"
            f"Question: {task.input_ref}"
        )

    raise ValueError(f"Unhandled AI task type: {task.task_type}")


async def _load_job_context(db: AsyncSession, job_id: uuid.UUID) -> str:
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one()
    customer = (await db.execute(select(Customer).where(Customer.id == job.customer_id))).scalar_one()

    notes_result = await db.execute(
        select(JobStatusHistory.note)
        .where(JobStatusHistory.job_id == job.id, JobStatusHistory.note.is_not(None))
        .order_by(JobStatusHistory.created_at)
    )
    notes = [note for (note,) in notes_result.all()]

    lines = [
        f"Customer: {customer.full_name}",
        f"Status: {job.status.value}",
        f"Reported issue: {job.reported_issue}",
    ]
    if notes:
        lines.append("Timeline notes:")
        lines.extend(f"- {note}" for note in notes)
    return "\n".join(lines)


async def _load_org_query_context(db: AsyncSession, organization_id: uuid.UUID) -> str:
    result = await db.execute(
        select(Job)
        .where(Job.organization_id == organization_id)
        .order_by(Job.created_at.desc())
        .limit(_QA_CONTEXT_JOB_LIMIT)
    )
    jobs = result.scalars().all()
    if not jobs:
        return "(no jobs recorded yet)"

    lines = []
    for job in jobs:
        lines.append(
            f"- [{job.created_at.date().isoformat()}] status={job.status.value}: {job.reported_issue}"
        )
    return "\n".join(lines)


async def _call_claude(prompt: str) -> str:
    # No `thinking` / `output_config.effort` here: those are Opus/Sonnet
    # 5-tier parameters and Haiku 4.5 rejects `effort` outright (400) —
    # Haiku 4.5 has no extended-thinking or effort control at all, so a
    # plain non-streaming call is the correct (and only) shape for it.
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_OUTPUT_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")
