import { apiFetch } from "@/services/apiClient";
import type { ReviewCase, ReviewCaseStatus } from "@/types/api";

export function fetchReviews(
  accessToken: string | undefined,
  status?: ReviewCaseStatus,
): Promise<ReviewCase[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const query = params.toString();
  return apiFetch<{ reviews: ReviewCase[] }>(`/reviews${query ? `?${query}` : ""}`, { accessToken }).then(
    (r) => r.reviews,
  );
}

export function resolveReview(
  accessToken: string | undefined,
  reviewId: string,
  status: "in_review" | "closed",
): Promise<{ review: ReviewCase }> {
  return apiFetch(`/reviews/${reviewId}/resolve`, { accessToken, method: "POST", body: { status } });
}
