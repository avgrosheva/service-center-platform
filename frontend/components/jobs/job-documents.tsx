'use client';

/**
 * Milestone F12 — trigger document generation and list/download the
 * results. Generation is backend-async (`BackgroundTasks`): the POST
 * returns 202 immediately, before the PDF actually exists. Rather than a
 * full polling UI, this does a short bounded poll (up to ~8 attempts,
 * 1.5s apart — a few seconds total) after triggering, stopping the
 * moment a new document shows up; if it's still not there after that
 * window, it says so plainly instead of polling forever.
 */

import { useEffect, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { ApiError, browserApiClient } from '@/lib/api-client';
import type { DocumentGenerateRequest, DocumentType, JobDocument } from '@/types/api';

const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = {
  job_report: 'Job report',
  repair_certificate: 'Repair certificate',
};

const POLL_INTERVAL_MS = 1500;
const MAX_POLL_ATTEMPTS = 8;

export function JobDocuments({ jobId, onActivity }: { jobId: string; onActivity?: () => void }) {
  const [documents, setDocuments] = useState<JobDocument[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState<DocumentType | null>(null);
  const [pollingNote, setPollingNote] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  // Tracks whether the component is *currently* mounted, for the polling
  // loop in handleGenerate below (which can easily outlive a single
  // effect run). Reset to `true` at the start of every effect run, not
  // just set `false` in cleanup — React's Strict Mode double-invokes
  // mount effects in development (mount -> cleanup -> mount again), and
  // only setting `false` in cleanup without resetting `true` on the next
  // mount would leave this permanently stuck `false` after that first
  // simulated cleanup, silently killing every future poll before its
  // first iteration.
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    let cancelled = false;
    void (async () => {
      try {
        const data = await browserApiClient<JobDocument[]>(`/jobs/${jobId}/documents`);
        if (!cancelled) setDocuments(data);
      } catch (err) {
        if (!cancelled)
          setLoadError(err instanceof ApiError ? err.detail : 'Failed to load documents.');
      }
    })();
    return () => {
      cancelled = true;
      isMountedRef.current = false;
    };
  }, [jobId]);

  const handleGenerate = async (type: DocumentType) => {
    setTriggering(type);
    setActionError(null);
    setPollingNote(null);
    const countBefore = documents?.length ?? 0;
    try {
      await browserApiClient(`/jobs/${jobId}/documents`, {
        method: 'POST',
        body: { type } as DocumentGenerateRequest,
      });

      for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
        if (!isMountedRef.current) return;
        const data = await browserApiClient<JobDocument[]>(`/jobs/${jobId}/documents`);
        if (data.length > countBefore) {
          setDocuments(data);
          setTriggering(null);
          onActivity?.();
          return;
        }
      }
      setPollingNote('Still generating — check back in a moment and reload this section.');
    } catch (err) {
      setActionError(err instanceof ApiError ? err.detail : 'Failed to generate document.');
    } finally {
      setTriggering(null);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {loadError && <p className="text-sm text-destructive">{loadError}</p>}
      {actionError && <p className="text-sm text-destructive">{actionError}</p>}

      {documents === null ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>
      ) : documents.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">No documents generated yet.</p>
      ) : (
        <ul className="flex flex-col gap-1 text-sm">
          {documents.map((doc) => (
            <li key={doc.id} className="flex items-center justify-between gap-2">
              <span>
                {DOCUMENT_TYPE_LABELS[doc.type]}
                <span className="ml-2 text-xs text-zinc-500 dark:text-zinc-400">
                  {new Date(doc.generated_at).toLocaleString()}
                </span>
              </span>
              <a
                href={doc.download_url}
                target="_blank"
                rel="noreferrer"
                className="text-sm underline"
              >
                Download
              </a>
            </li>
          ))}
        </ul>
      )}

      {pollingNote && <p className="text-sm text-zinc-500 dark:text-zinc-400">{pollingNote}</p>}

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          disabled={triggering !== null}
          onClick={() => void handleGenerate('job_report')}
        >
          {triggering === 'job_report' ? 'Generating…' : 'Generate report'}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={triggering !== null}
          onClick={() => void handleGenerate('repair_certificate')}
        >
          {triggering === 'repair_certificate' ? 'Generating…' : 'Generate certificate'}
        </Button>
      </div>
    </div>
  );
}
