export type Mode = 'stub' | 'deterministic_demo' | 'agent';
export interface Meta {
  schema_version: string; execution_mode: Mode; demo_today: string; disclaimer: string;
  dataset_version: string | null;
  provenance: { source_type: string; source_name: string; source_date: string; demo_only: boolean } | null;
  features: Record<string, boolean>;
  supported_operations?: string[];
  planning_stages?: Record<string,string>;
  agent_configuration_error?: ApiError['error'] | null;
}
export interface Ready {
  status: 'ready' | 'not_ready'; execution_mode: Mode;
  checks: { dataset_readable: boolean; dataset_context_valid: boolean; sqlite_driver: boolean; database_migrated: boolean; configured_agent_available: boolean };
  missing_files: string[]; business_persistence_implemented: boolean; real_agents_implemented: boolean;
  agent_configuration_error?: ApiError['error'] | null;
}
export interface ApiError {
  error: { code: string; message: string; recoverable: boolean; field_errors: { field: string; message: string }[]; allowed_actions: string[]; context: Record<string, string> };
  trace_id: string;
}
export interface Requirements {
  destination: string | null; start_date: string | null; duration_nights: number | null;
  end_date: string | null; duration_days: number | null; budget_cents: number | null;
  currency: 'AUD'; preferences: string[]; mandatory_constraints: string[];
}
export interface PreviewResult {
  schema_version: string; execution_mode: Mode; extracted_requirements: Requirements;
  clarifications: { field: string; question: string; reason: string }[];
  field_errors: { field: string; message: string }[];
  uncertainties: string[]; assumptions: string[]; source_refs: unknown[];
}
export class ApiFailure extends Error {
  constructor(public readonly envelope: ApiError) { super(envelope.error.message); }
}
async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`服务返回 HTTP ${response.status}`);
  return response.json() as Promise<T>;
}
export async function loadStatus(signal?: AbortSignal): Promise<{ meta: Meta; ready: Ready }> {
  const [meta, response] = await Promise.all([getJson<Meta>('/api/v1/meta', signal), fetch('/api/v1/health/ready', { signal })]);
  if (response.status !== 200 && response.status !== 503) throw new Error('无法读取服务就绪状态。');
  return { meta, ready: await response.json() as Ready };
}
export async function previewRequest(raw_text: string, explicit_fields: Partial<Requirements>): Promise<PreviewResult> {
  const response = await fetch('/api/v1/dev/interpret', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ raw_text, explicit_fields }) });
  const body = await response.json();
  if (!response.ok) throw new ApiFailure(body as ApiError);
  return body as PreviewResult;
}
