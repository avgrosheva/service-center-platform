import { JOB_STATUS_LABELS } from '@/components/jobs/job-status-badge';
import type { JobStatusHistoryEntry } from '@/types/api';

// Milestones F10-F12 own the features that actually produce these event
// types (photos, materials, additional work, documents) — none of them can
// occur yet, but the timeline renders every known type "placeholder-
// friendly" per the F9 roadmap spec, so nothing here needs revisiting once
// those milestones land and start writing real rows of these kinds.
const EVENT_TYPE_LABELS: Record<string, string> = {
  status_changed: 'Status changed',
  assigned: 'Technician assigned',
  photo_added: 'Photo added',
  material_added: 'Material added',
  material_edited: 'Material edited',
  material_removed: 'Material removed',
  additional_work_flagged: 'Additional work flagged',
  additional_work_approved: 'Additional work approved',
  additional_work_rejected: 'Additional work rejected',
  additional_work_billed: 'Additional work billed',
  document_generated: 'Document generated',
};

function describeEntry(entry: JobStatusHistoryEntry): string {
  if (entry.event_type === 'status_changed' && entry.from_status && entry.to_status) {
    return `${JOB_STATUS_LABELS[entry.from_status]} → ${JOB_STATUS_LABELS[entry.to_status]}`;
  }
  if (entry.note) return entry.note;
  return EVENT_TYPE_LABELS[entry.event_type] ?? entry.event_type;
}

export function JobTimeline({
  entries,
  actorNameById,
}: {
  entries: JobStatusHistoryEntry[];
  /** Owner/dispatcher viewers can resolve any actor; a technician viewer only ever resolves themselves. */
  actorNameById: Record<string, string>;
}) {
  if (entries.length === 0) {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">No activity yet.</p>;
  }

  return (
    <ul className="flex flex-col gap-3 text-sm">
      {entries.map((entry) => {
        const header = EVENT_TYPE_LABELS[entry.event_type] ?? entry.event_type;
        const detail = describeEntry(entry);
        return (
          <li
            key={entry.id}
            className="flex flex-col gap-0.5 border-l-2 border-zinc-200 pl-3 dark:border-zinc-800"
          >
            <span className="font-medium">{header}</span>
            {detail !== header && (
              <span className="text-zinc-600 dark:text-zinc-400">{detail}</span>
            )}
            <span className="text-xs text-zinc-500 dark:text-zinc-500">
              {new Date(entry.created_at).toLocaleString()}
              {entry.actor_id && actorNameById[entry.actor_id]
                ? ` · ${actorNameById[entry.actor_id]}`
                : ''}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
