export interface Tenant {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  created_at: string;
}

export type DecisionOutcome = "approve" | "refer" | "decline";

export interface Decision {
  id: string;
  tenant_id: string;
  model_version_id: string;
  application_reference: string;
  request_id: string;
  score: number;
  outcome: DecisionOutcome;
  created_at: string;
}

export interface ReasonCode {
  rank: number;
  feature: string;
  label: string;
  contribution: number;
  direction: "increased_risk" | "decreased_risk" | "no_effect";
}

export interface Explanation {
  id: string;
  decision_id: string;
  method: string;
  base_value: number;
  feature_attributions: Record<string, number>;
  // A ranked, human-readable view of feature_attributions (top 5 by
  // |contribution|) -- a pure deterministic transform of the SHAP values
  // above, computed server-side (app/services/reason_codes.py), never a
  // generative model inventing reasons (CLAUDE.md).
  reason_codes: ReasonCode[];
  created_at: string;
}

export type ModelVersionStatus = "draft" | "approved" | "deployed" | "archived";

export interface ModelVersion {
  id: string;
  model_id: string;
  version: string;
  status: ModelVersionStatus;
  artifact_uri: string;
  metrics: Record<string, unknown> | null;
  created_at: string;
}

export interface Model {
  id: string;
  tenant_id: string;
  name: string;
  created_at: string;
  versions: ModelVersion[];
}

export interface ModelDeployment {
  id: string;
  tenant_id: string;
  model_version_id: string;
  status: "active" | "rolled_back";
  deployed_at: string;
  rolled_back_at: string | null;
}

export interface Dataset {
  id: string;
  tenant_id: string;
  name: string;
  created_at: string;
  versions: DatasetVersion[];
}

export interface DatasetVersion {
  id: string;
  dataset_id: string;
  version: string;
  uri: string;
  row_count: number | null;
  created_at: string;
}

export interface AuditEvent {
  id: string;
  tenant_id: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  hash: string;
  prev_hash: string | null;
  created_at: string;
}

export interface AuditExportEvent extends AuditEvent {
  payload: Record<string, unknown>;
}

export interface AuditExportResponse {
  events: AuditExportEvent[];
  meta: {
    exported_by: string;
    exported_at: string;
    scope: { date_from: string | null; date_to: string | null };
    event_count: number;
    export_event_id: string;
  };
}

export interface MonitoringAlert {
  id: string;
  tenant_id: string;
  alert_type: string;
  severity: "low" | "medium" | "high" | "critical";
  message: string;
  status: "open" | "acknowledged" | "resolved";
  created_at: string;
  resolved_at: string | null;
}

export interface CurrentModelVersion {
  model_id: string;
  model_name: string;
  model_version_id: string;
  version: string;
}

export interface MonitoringMetrics {
  decision_count: number;
  approved_count: number;
  // null means "no decisions yet", not "0%" — the UI must show these
  // differently.
  approval_rate: number | null;
  deployed_model_count: number;
  current_model_version: CurrentModelVersion | null;
}

// null fields mean "no observations yet in this process", not zero —
// same null-vs-zero discipline as MonitoringMetrics.approval_rate above.
export interface HistogramSummary {
  count: number;
  sum_seconds: number;
  avg_ms: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
}

export interface ObservabilitySummary {
  http: {
    total_requests: number;
    requests_by_status: Record<string, number>;
    error_rate: number | null;
    unhandled_exceptions: number;
    latency: HistogramSummary;
  };
  scoring: {
    requests_by_outcome: Record<string, number>;
    runtime_errors: number;
    duration: HistogramSummary;
  };
  model_inference: { duration: HistogramSummary };
  explanation: { duration: HistogramSummary };
  database: { errors: number; query_duration: HistogramSummary };
  outbox: { events_by_status: Record<string, number> };
  governance: { results_by_outcome: Record<string, number> };
  review_cases: { opened_by_reason: Record<string, number> };
}

export interface FairnessEvaluation {
  id: string;
  tenant_id: string;
  model_version_id: string;
  protected_attribute: string;
  metric_name: string;
  metric_value: number;
  threshold: number;
  passed: boolean;
  created_at: string;
}

export interface AuditIntegrityCheckRecord {
  id: string;
  tenant_id: string;
  checked_from_event_id: string | null;
  checked_to_event_id: string | null;
  valid: boolean;
  created_at: string;
}

export interface AuditChainVerification {
  valid: boolean;
  events_checked: number;
  first_event_id: string | null;
  last_event_id: string | null;
  failures: { event_id: string; reason: string }[];
  integrity_check_id: string;
}

export interface HealthStatus {
  status: string;
}

export interface ReadinessStatus {
  status: string;
  dependencies: { database: boolean };
}

export interface ApiErrorBody {
  error: string;
}

export type ReviewCaseStatus = "open" | "in_review" | "closed";

export interface ReviewCaseDecisionSummary {
  id: string;
  application_reference: string;
  score: number;
  outcome: DecisionOutcome;
  model_version_id: string;
  created_at: string;
}

export interface ReviewCase {
  id: string;
  tenant_id: string;
  decision_id: string;
  assigned_to: string | null;
  status: ReviewCaseStatus;
  reason: string | null;
  created_at: string;
  resolved_at: string | null;
  decision: ReviewCaseDecisionSummary | null;
}
