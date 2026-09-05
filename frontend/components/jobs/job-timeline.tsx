'use client';

import { useLocale } from '@/lib/i18n/context';
import type { TranslationKey } from '@/lib/i18n/context';
import type { JobStatusHistoryEntry } from '@/types/api';

// Milestones F10-F12 own the features that actually produce these event
// types (photos, materials, additional work, documents) — none of them can
// occur yet, but the timeline renders every known type "placeholder-
// friendly" per the F9 roadmap spec, so nothing here needs revisiting once
// those milestones land and start writing real rows of these kinds.
const EVENT_TYPE_KEYS: Record<string, TranslationKey> = {
  status_changed: 'timelineEvents.status_changed',
  assigned: 'timelineEvents.assigned',
  photo_added: 'timelineEvents.photo_added',
  material_added: 'timelineEvents.material_added',
  material_edited: 'timelineEvents.material_edited',
  material_removed: 'timelineEvents.material_removed',
  additional_work_flagged: 'timelineEvents.additional_work_flagged',
  additional_work_approved: 'timelineEvents.additional_work_approved',
  additional_work_rejected: 'timelineEvents.additional_work_rejected',
  additional_work_billed: 'timelineEvents.additional_work_billed',
  document_generated: 'timelineEvents.document_generated',
};

const PHOTO_TAG_KEYS: Record<string, TranslationKey> = {
  before: 'jobPhotos.before',
  after: 'jobPhotos.after',
  general: 'jobPhotos.general',
};

const DOCUMENT_TYPE_KEYS: Record<string, TranslationKey> = {
  job_report: 'jobDocuments.jobReport',
  repair_certificate: 'jobDocuments.repairCertificate',
};

const ASSIGNED_NOTE = /^Assigned to (.+)$/;
const PHOTO_ADDED_NOTE = /^Photo added(?: \((\w+)\))?$/;
const MATERIAL_NOTE = /^Material (?:added|edited|removed): (.+)$/;
const ADDITIONAL_WORK_NOTE = /^Additional work \w+: (.+)$/;
const DOCUMENT_GENERATED_NOTE = /^(\w+) generated$/;

export function JobTimeline({
  entries,
  actorNameById,
}: {
  entries: JobStatusHistoryEntry[];
  /** Owner/dispatcher viewers can resolve any actor; a technician viewer only ever resolves themselves. */
  actorNameById: Record<string, string>;
}) {
  const { t } = useLocale();

  const eventLabel = (eventType: string): string => {
    const key = EVENT_TYPE_KEYS[eventType];
    return key ? t(key) : eventType;
  };

  // The backend always writes `note` as fixed English boilerplate (see
  // job_service.py / job_items_service.py / document_tasks.py) wrapping one
  // piece of real data — a technician's name, a material's name, a document
  // type — that data itself isn't UI copy and is shown as-is; only the
  // boilerplate wrapper needs translating, so each case below peels the
  // wrapper off via the note's known fixed shape rather than showing the
  // raw English sentence. A `note` that doesn't match its event type's
  // known shape (a backend format that moved on without this catching up)
  // falls through to the raw text rather than disappearing silently.
  const describeEntry = (entry: JobStatusHistoryEntry): string => {
    if (entry.event_type === 'status_changed' && entry.from_status && entry.to_status) {
      return `${t(`jobStatus.${entry.from_status}`)} → ${t(`jobStatus.${entry.to_status}`)}`;
    }

    switch (entry.event_type) {
      case 'assigned': {
        const match = entry.note?.match(ASSIGNED_NOTE);
        if (match) return match[1];
        break;
      }
      case 'photo_added': {
        const match = entry.note?.match(PHOTO_ADDED_NOTE);
        if (match) {
          const tagKey = match[1] ? PHOTO_TAG_KEYS[match[1]] : undefined;
          return tagKey ? t(tagKey) : eventLabel(entry.event_type);
        }
        break;
      }
      case 'material_added':
      case 'material_edited':
      case 'material_removed': {
        const match = entry.note?.match(MATERIAL_NOTE);
        if (match) return match[1];
        break;
      }
      case 'additional_work_flagged':
      case 'additional_work_approved':
      case 'additional_work_rejected':
      case 'additional_work_billed': {
        const match = entry.note?.match(ADDITIONAL_WORK_NOTE);
        if (match) return match[1];
        break;
      }
      case 'document_generated': {
        const match = entry.note?.match(DOCUMENT_GENERATED_NOTE);
        const typeKey = match ? DOCUMENT_TYPE_KEYS[match[1]] : undefined;
        if (typeKey) return t(typeKey);
        break;
      }
    }

    if (entry.note) return entry.note;
    return eventLabel(entry.event_type);
  };

  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">{t('jobTimeline.noActivityYet')}</p>;
  }

  return (
    <ul className="flex flex-col gap-3 text-sm">
      {entries.map((entry) => {
        const header = eventLabel(entry.event_type);
        const detail = describeEntry(entry);
        return (
          <li key={entry.id} className="flex flex-col gap-0.5 border-l-2 border-border pl-3">
            <span className="font-medium">{header}</span>
            {detail !== header && <span className="text-muted-foreground">{detail}</span>}
            <span className="text-xs text-muted-foreground">
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
