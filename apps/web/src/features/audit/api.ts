import { apiFetch } from "@/services/apiClient";
import type { AuditChainVerification, AuditEvent, AuditIntegrityCheckRecord } from "@/types/api";

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
