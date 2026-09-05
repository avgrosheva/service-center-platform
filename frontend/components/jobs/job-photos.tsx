'use client';

/**
 * Milestone F10 — photo upload section. The three-step flow (per the
 * roadmap's own emphasis on getting this exactly right):
 *
 * 1. POST /jobs/{id}/photos/upload-url — get a presigned S3 PUT URL + the
 *    s3_key it was signed for.
 * 2. PUT the raw file bytes directly to that URL — this goes straight to
 *    the storage bucket (MinIO locally), NOT through this app's own
 *    proxy/backend at all, so it's a plain `fetch`, not `browserApiClient`.
 * 3. POST /jobs/{id}/photos with that s3_key — confirms the upload and
 *    persists the metadata row; the response includes a fresh presigned
 *    `view_url` (added alongside this milestone — see
 *    app/schemas/photo.py) for the thumbnail grid.
 *
 * A single `pending` state machine covers all three steps under one
 * loading UI (not just the first request), and remembers which step
 * failed so retrying resumes from there — re-requesting a fresh upload
 * URL after the file already reached the bucket, or re-uploading a file
 * that already has a valid presigned URL, would both be wrong.
 */

import { useEffect, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { useLocale } from '@/lib/i18n/context';
import type { TranslationKey } from '@/lib/i18n/context';
import { ApiError, browserApiClient } from '@/lib/api-client';
import type {
  Photo,
  PhotoCreateRequest,
  PhotoTag,
  PhotoUploadUrlRequest,
  PhotoUploadUrlResponse,
} from '@/types/api';

const ACCEPTED_CONTENT_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/heic'];

type UploadStep = 'url' | 'upload' | 'confirm';

type PendingUpload = {
  file: File;
  tag: PhotoTag | '';
  step: UploadStep;
  uploadUrl?: string;
  s3Key?: string;
  error?: string;
};

const TAG_KEYS: Record<PhotoTag, TranslationKey> = {
  before: 'jobPhotos.before',
  after: 'jobPhotos.after',
  general: 'jobPhotos.general',
};

export function JobPhotos({
  jobId,
  onActivity,
  large,
}: {
  jobId: string;
  onActivity?: () => void;
  /** Milestone F13 — a bigger, full-width upload trigger for a technician's one-handed mobile view. */
  large?: boolean;
}) {
  const { t } = useLocale();
  const [photos, setPhotos] = useState<Photo[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedTag, setSelectedTag] = useState<PhotoTag | ''>('');
  const [fileTypeError, setFileTypeError] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingUpload | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await browserApiClient<Photo[]>(`/jobs/${jobId}/photos`);
        if (!cancelled) setPhotos(data);
      } catch (err) {
        if (!cancelled)
          setLoadError(err instanceof ApiError ? err.detail : t('jobPhotos.failedToLoad'));
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const runFromStep = async (upload: PendingUpload) => {
    let { step, uploadUrl, s3Key } = upload;
    const { file, tag } = upload;

    try {
      if (step === 'url') {
        setPending({ file, tag, step: 'url' });
        const resp = await browserApiClient<PhotoUploadUrlResponse>(
          `/jobs/${jobId}/photos/upload-url`,
          {
            method: 'POST',
            body: { content_type: file.type } as PhotoUploadUrlRequest,
          },
        );
        uploadUrl = resp.upload_url;
        s3Key = resp.s3_key;
        step = 'upload';
      }

      if (step === 'upload') {
        setPending({ file, tag, step: 'upload', uploadUrl, s3Key });
        const putRes = await fetch(uploadUrl!, {
          method: 'PUT',
          headers: { 'Content-Type': file.type },
          body: file,
        });
        if (!putRes.ok) {
          throw new Error(`Upload to storage failed (HTTP ${putRes.status}).`);
        }
        step = 'confirm';
      }

      setPending({ file, tag, step: 'confirm', uploadUrl, s3Key });
      const created = await browserApiClient<Photo>(`/jobs/${jobId}/photos`, {
        method: 'POST',
        body: { s3_key: s3Key!, tag: tag || undefined } as PhotoCreateRequest,
      });

      setPhotos((prev) => (prev ? [...prev, created] : [created]));
      setPending(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      onActivity?.();
    } catch (err) {
      setPending({
        file,
        tag,
        step,
        uploadUrl,
        s3Key,
        error:
          err instanceof ApiError
            ? err.detail
            : err instanceof Error
              ? err.message
              : t('jobPhotos.uploadFailed'),
      });
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileTypeError(null);
    if (!ACCEPTED_CONTENT_TYPES.includes(file.type)) {
      setFileTypeError(t('jobPhotos.unsupportedFileType', { type: file.type || 'unknown' }));
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }
    void runFromStep({ file, tag: selectedTag, step: 'url' });
  };

  return (
    <div className="flex flex-col gap-3">
      {loadError && <p className="text-sm text-destructive">{loadError}</p>}

      {photos === null ? (
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      ) : photos.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('jobPhotos.noPhotosYet')}</p>
      ) : (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {photos.map((photo) => (
            <a
              key={photo.id}
              href={photo.view_url}
              target="_blank"
              rel="noreferrer"
              className="group flex flex-col gap-1"
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- presigned S3/MinIO URLs, not a static/local asset next/image can optimize */}
              <img
                src={photo.view_url}
                alt={photo.tag ?? 'Job photo'}
                className="aspect-square w-full rounded-md object-cover ring-1 ring-border group-hover:opacity-90"
              />
              {photo.tag && (
                <span className="text-xs text-muted-foreground">{t(TAG_KEYS[photo.tag])}</span>
              )}
            </a>
          ))}
        </div>
      )}

      <div className={large ? 'flex flex-col gap-2' : 'flex flex-wrap items-center gap-2'}>
        <select
          value={selectedTag}
          onChange={(e) => setSelectedTag(e.target.value as PhotoTag | '')}
          disabled={pending !== null && !pending.error}
          className={
            large
              ? 'h-11 w-full rounded-lg border border-input bg-transparent px-3 text-base outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30'
              : 'h-8 rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30'
          }
        >
          <option value="">{t('jobPhotos.noTag')}</option>
          <option value="before">{t('jobPhotos.before')}</option>
          <option value="after">{t('jobPhotos.after')}</option>
          <option value="general">{t('jobPhotos.general')}</option>
        </select>
        <Button
          type="button"
          variant="outline"
          onClick={() => fileInputRef.current?.click()}
          disabled={pending !== null && !pending.error}
          className={large ? 'h-12 w-full text-base' : undefined}
        >
          {pending && !pending.error
            ? pending.step === 'url'
              ? t('jobPhotos.requestingUploadUrl')
              : pending.step === 'upload'
                ? t('jobPhotos.uploading')
                : t('common.saving')
            : t('jobPhotos.uploadPhoto')}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_CONTENT_TYPES.join(',')}
          onChange={handleFileChange}
          className="hidden"
        />
      </div>

      {fileTypeError && <p className="text-sm text-destructive">{fileTypeError}</p>}

      {pending?.error && (
        <div className="flex flex-col gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2">
          <p className="text-sm text-destructive">{pending.error}</p>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => void runFromStep(pending)}>
              {t('jobPhotos.retry')}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() =>
                void runFromStep({ file: pending.file, tag: pending.tag, step: 'url' })
              }
            >
              {t('jobPhotos.startOver')}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setPending(null)}>
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
