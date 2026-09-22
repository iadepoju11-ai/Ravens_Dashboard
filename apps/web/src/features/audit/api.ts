import { apiFetch } from "@/services/apiClient";
import type { AuditChainVerification, AuditEvent, AuditExportResponse, AuditIntegrityCheckRecord } from "@/types/api";

export interface AuditExportScope {
  dateFrom?: string;
  dateTo?: string;
}

export function exportAuditEvents(
  accessToken: string | undefined,
  scope: AuditExportScope,
): Promise<AuditExportResponse> {
  const params = new URLSearchParams();
  if (scope.dateFrom) params.set("date_from", scope.dateFrom);
  if (scope.dateTo) params.set("date_to", scope.dateTo);
  const query = params.toString();
  return apiFetch(`/audit/export${query ? `?${query}` : ""}`, { accessToken });
}

export function fetchAuditEvents(accessToken: string | undefined): Promise<AuditEvent[]> {
  return apiFetch<{ events: AuditEvent[] }>("/audit/events", { accessToken }).then((r) => r.events);
}

export function fetchIntegrityStatus(accessToken: string | undefined): Promise<AuditIntegrityCheckRecord | null> {
  return apiFetch<{ latest_check: AuditIntegrityCheckRecord | null }>("/audit/integrity-status", {
    accessToken,
  }).then((r) => r.latest_check);
}

export function verifyChain(accessToken: string | undefined): Promise<AuditChainVerification> {
  return apiFetch("/audit/verify-chain", { accessToken });
}

export function verifyEvent(
  accessToken: string | undefined,
  eventId: string,
): Promise<{ event_id: string; valid: boolean; integrity_check_id: string }> {
  return apiFetch(`/audit/events/${eventId}/verify`, { accessToken });
}
