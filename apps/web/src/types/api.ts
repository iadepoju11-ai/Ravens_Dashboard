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
