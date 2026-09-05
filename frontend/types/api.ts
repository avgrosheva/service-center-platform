/**
 * TypeScript types mirroring the backend's Pydantic schemas (Milestone F1).
 *
 * Hand-written to match `app/schemas/*.py` in the backend repo — there is
 * no shared codegen step in this stack, so these must be kept in sync
 * manually whenever a backend schema changes.
 *
 * Every field's exact JSON shape was spot-checked against the running
 * backend (not just read from the Pydantic source), because a few things
 * don't serialize the way you'd guess from the Python type alone:
 *
 * - **`Decimal` fields serialize as JSON strings, not numbers** — e.g.
 *   `MaterialItem.quantity`, `AdditionalWorkItem.price`, `Payment.amount`
 *   all come back as `"45.00"`, not `45.00`. Confirmed via real POST/GET
 *   responses, not assumed from the Python `Decimal` type. Typed as
 *   `DecimalString` below — never `number` — and any arithmetic on these
 *   values must parse them explicitly first.
 * - **Datetimes serialize as ISO 8601 UTC strings with a `Z` suffix**
 *   (e.g. `"2026-08-31T21:48:02.446161Z"`). Typed as `IsoDateTime`.
 * - **`date`-only fields** (no time component — `install_date`,
 *   `warranty_until`, `warranty_expires_at`) are typed as `IsoDate`,
 *   distinct from `IsoDateTime`, since they're a different backend type
 *   (`datetime.date` vs `datetime.datetime`) with a different string
 *   shape (`"2026-08-31"`, no time/offset).
 */

// --- Primitive aliases (all still plain strings at runtime — these exist
// purely so a reader/reviewer can see intent at the type level) ---

export type Uuid = string;
/** ISO 8601 datetime, UTC, `Z`-suffixed — e.g. "2026-08-31T21:48:02.446161Z". */
export type IsoDateTime = string;
/** ISO 8601 date only, no time component — e.g. "2026-08-31". */
export type IsoDate = string;
/** A Decimal serialized as a JSON string — e.g. "45.00". Parse before doing arithmetic. */
export type DecimalString = string;

// --- Enums (string literal unions, matching the backend's str Enum values exactly) ---

export type UserRole = 'owner' | 'dispatcher' | 'technician';

export type JobStatus =
  | 'new'
  | 'assigned'
  | 'en_route'
  | 'in_progress'
  | 'awaiting_parts'
  | 'awaiting_approval'
  | 'completed'
  | 'cancelled';

/**
 * `job_status_history.event_type` — a plain string on the backend (no DB
 * CHECK constraint, see the backend's job_status_history.py docstring for
 * why), so this union is the Python-side JobEventType's values, not a
 * database-enforced set. Treat it as "the known values so far", not
 * exhaustive by construction — a future backend milestone could add one
 * without a type error here until this file is updated to match.
 */
export type JobEventType =
  | 'status_changed'
  | 'assigned'
  | 'photo_added'
  | 'material_added'
  | 'material_edited'
  | 'material_removed'
  | 'additional_work_flagged'
  | 'additional_work_approved'
  | 'additional_work_rejected'
  | 'additional_work_billed'
  | 'document_generated';

export type PhotoTag = 'before' | 'after' | 'general';

export type PhotoContentType = 'image/jpeg' | 'image/png' | 'image/webp' | 'image/heic';

export type AdditionalWorkStatus = 'pending' | 'approved' | 'rejected' | 'billed';

export type PaymentMethod = 'cash' | 'card' | 'bank_transfer' | 'other';

export type PaymentStatus = 'unpaid' | 'paid';

export type DocumentType = 'job_report' | 'repair_certificate';

export type AITaskType =
  'voice_transcription' | 'summary' | 'additional_work_suggestion' | 'qa_query';

export type AITaskStatus = 'pending' | 'processing' | 'done' | 'failed';

// --- Organization ---

export interface Organization {
  id: Uuid;
  name: string;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

// --- User ---

export interface User {
  id: Uuid;
  organization_id: Uuid;
  email: string;
  full_name: string;
  role: UserRole;
  phone: string | null;
  // Only ever populated on `/auth/me` responses (the signed-in user's own
  // profile) — omitted (not just null) on every other User read, like the
  // org's user roster in Settings, since generating a presigned URL for
  // every row there would be wasted work for avatars nothing renders.
  avatar_url?: string | null;
  is_active: boolean;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface UserCreateRequest {
  email: string;
  full_name: string;
  role: UserRole;
  password: string;
}

export interface UserUpdateRequest {
  role?: UserRole;
  is_active?: boolean;
  /** Owner resetting a teammate's forgotten password — bypasses the current-password check /auth/me/password requires, since the caller is an admin acting on someone else's account, not the account holder. */
  password?: string;
}

export interface MeUpdateRequest {
  full_name?: string;
  email?: string;
  /** `""` clears it — the one field on this request that's nullable. */
  phone?: string;
}

export interface PasswordChangeRequest {
  current_password: string;
  new_password: string;
}

export interface AvatarUploadUrlRequest {
  content_type: PhotoContentType;
}

export interface AvatarUploadUrlResponse {
  upload_url: string;
  s3_key: string;
}

export interface AvatarConfirmRequest {
  s3_key: string;
}

// --- Auth ---

export interface RegisterRequest {
  organization_name: string;
  full_name: string;
  email: string;
  password: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface AccessTokenResponse {
  access_token: string;
  token_type: string;
}

// --- Customer ---

export interface Customer {
  id: Uuid;
  organization_id: Uuid;
  full_name: string;
  phone: string;
  notes: string | null;
  is_active: boolean;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface CustomerCreateRequest {
  full_name: string;
  phone: string;
  notes?: string | null;
}

export interface CustomerUpdateRequest {
  full_name?: string;
  phone?: string;
  notes?: string | null;
  is_active?: boolean;
}

// --- Equipment ---

export interface Equipment {
  id: Uuid;
  organization_id: Uuid;
  customer_id: Uuid;
  type: string;
  brand: string | null;
  model: string | null;
  serial_number: string | null;
  installation_address: string;
  install_date: IsoDate | null;
  warranty_until: IsoDate | null;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface EquipmentCreateRequest {
  type: string;
  brand?: string | null;
  model?: string | null;
  serial_number?: string | null;
  installation_address: string;
  install_date?: IsoDate | null;
  warranty_until?: IsoDate | null;
}

export interface EquipmentUpdateRequest {
  type?: string;
  brand?: string | null;
  model?: string | null;
  serial_number?: string | null;
  installation_address?: string;
  install_date?: IsoDate | null;
  warranty_until?: IsoDate | null;
}

// --- Job ---

export interface Job {
  id: Uuid;
  organization_id: Uuid;
  customer_id: Uuid;
  equipment_id: Uuid | null;
  assigned_technician_id: Uuid | null;
  created_by_id: Uuid;
  status: JobStatus;
  reported_issue: string;
  address_snapshot: string;
  scheduled_at: IsoDateTime | null;
  completed_at: IsoDateTime | null;
  is_warranty_claim: boolean;
  origin_job_id: Uuid | null;
  warranty_expires_at: IsoDate | null;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface JobCreateRequest {
  customer_id: Uuid;
  equipment_id?: Uuid | null;
  reported_issue: string;
  /** Required when equipment_id is omitted; ignored by the backend when equipment_id is set (address_snapshot is always derived from the equipment record in that case). */
  address?: string | null;
  scheduled_at?: IsoDateTime | null;
  /** null (default) lets the backend's auto-detection decide; true/false always overrides it. */
  is_warranty_claim?: boolean | null;
}

export interface JobUpdateRequest {
  reported_issue?: string;
  address_snapshot?: string;
  scheduled_at?: IsoDateTime | null;
}

export interface JobAssignRequest {
  technician_id: Uuid;
}

export interface JobStatusChangeRequest {
  status: JobStatus;
  note?: string | null;
}

export interface JobStatusHistoryEntry {
  id: Uuid;
  job_id: Uuid;
  actor_id: Uuid | null;
  event_type: JobEventType;
  from_status: JobStatus | null;
  to_status: JobStatus | null;
  note: string | null;
  created_at: IsoDateTime;
}

// --- Photo ---

export interface Photo {
  id: Uuid;
  job_id: Uuid;
  uploaded_by_id: Uuid;
  s3_key: string;
  tag: PhotoTag | null;
  created_at: IsoDateTime;
  /** A freshly generated, short-lived presigned GET URL — not persisted, regenerated on every read. Added post-Milestone-19 for Milestone F10 (see app/schemas/photo.py). */
  view_url: string;
}

export interface PhotoUploadUrlRequest {
  content_type: PhotoContentType;
}

export interface PhotoUploadUrlResponse {
  upload_url: string;
  s3_key: string;
}

export interface PhotoCreateRequest {
  s3_key: string;
  tag?: PhotoTag | null;
}

// --- MaterialItem ---

export interface MaterialItem {
  id: Uuid;
  job_id: Uuid;
  name: string;
  quantity: DecimalString;
  unit_cost: DecimalString | null;
  created_at: IsoDateTime;
}

export interface MaterialItemCreateRequest {
  name: string;
  /** A plain numeric string, e.g. "2.5" — sent as JSON string, matching how the backend echoes it back (see module docstring). */
  quantity: string;
  unit_cost?: string | null;
}

export interface MaterialItemUpdateRequest {
  name?: string;
  quantity?: string;
  unit_cost?: string | null;
}

// --- AdditionalWorkItem ---

export interface AdditionalWorkItem {
  id: Uuid;
  job_id: Uuid;
  description: string;
  price: DecimalString;
  status: AdditionalWorkStatus;
  created_by_id: Uuid;
  created_at: IsoDateTime;
}

export interface AdditionalWorkItemCreateRequest {
  description: string;
  price: string;
}

export interface AdditionalWorkItemStatusUpdateRequest {
  status: AdditionalWorkStatus;
}

// --- Payment ---

export interface Payment {
  id: Uuid;
  job_id: Uuid;
  amount: DecimalString;
  method: PaymentMethod;
  status: PaymentStatus;
  paid_at: IsoDateTime | null;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface PaymentUpsertRequest {
  amount: string;
  method: PaymentMethod;
  status?: PaymentStatus;
  paid_at?: IsoDateTime | null;
}

// --- Document ---

export interface JobDocument {
  id: Uuid;
  job_id: Uuid;
  type: DocumentType;
  s3_key: string;
  generated_at: IsoDateTime;
  /** A freshly generated, short-lived presigned GET URL — not persisted, regenerated on every read. Added post-Milestone-19 for Milestone F12 (see app/schemas/document.py), same gap/fix as Photo.view_url. */
  download_url: string;
}

export interface DocumentGenerateRequest {
  type?: DocumentType;
}

// --- AI (Milestone 18 — optional layer; see F16) ---

export interface AITask {
  id: Uuid;
  organization_id: Uuid;
  job_id: Uuid | null;
  task_type: AITaskType;
  status: AITaskStatus;
  input_ref: string;
  output: string | null;
  error: string | null;
  created_at: IsoDateTime;
  completed_at: IsoDateTime | null;
}

export interface VoiceNoteRequest {
  transcript: string;
}

export interface AIQueryRequest {
  query: string;
}

// --- Dashboard ---

export interface DashboardSummary {
  active_jobs: number;
  delayed_jobs: number;
  completed_jobs: number;
  unbilled_additional_work: number;
}

export interface TechnicianRevenue {
  technician_id: Uuid;
  technician_name: string;
  revenue: DecimalString;
}

export interface DashboardMetrics {
  avg_completion_time_hours: number | null;
  revenue_per_technician: TechnicianRevenue[];
  average_order_value: DecimalString | null;
  repeat_customer_rate: number;
  warranty_case_count: number;
}
