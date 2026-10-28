import { apiFetch, apiRequest } from "./client";
import {
  ComplaintCreatePayload,
  ComplaintListItem,
  ComplaintListQuery,
  ComplaintPage,
  ComplaintReopenPayload,
  ComplaintReopenResponse,
  ComplaintResponse,
  ComplaintStatusHistoryItem,
  DuplicateSuggestionsResponse,
} from "../types";

export function createComplaintApi(payload: ComplaintCreatePayload): Promise<ComplaintResponse> {
  const body: Record<string, unknown> = {
    title: payload.title,
    description: payload.description,
    department_id: payload.department_id,
  };
  if (typeof payload.is_public === "boolean") {
    body.is_public = payload.is_public;
  }
  if (typeof payload.floor_id === "number" && payload.floor_id > 0) {
    body.floor_id = payload.floor_id;
  }
  if (payload.hostel && payload.hostel.trim()) {
    body.hostel = payload.hostel.trim();
  }
  if (payload.wing && payload.wing.trim()) {
    body.wing = payload.wing.trim();
  }
  if (payload.floor && payload.floor.trim()) {
    body.floor = payload.floor.trim();
  }
  return apiFetch<ComplaintResponse>("/complaints", { method: "POST", body });
}

/** GET /complaints/mine — server-side search, filters and pagination with X-Total-Count. */
export async function getMyComplaintsApi(query: ComplaintListQuery = {}, signal?: AbortSignal): Promise<ComplaintPage> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  const { data, headers } = await apiRequest<ComplaintListItem[]>(`/complaints/mine${qs ? `?${qs}` : ""}`, { signal });
  const rawTotal = headers.get("X-Total-Count");
  const total = rawTotal !== null && /^\d+$/.test(rawTotal) ? Number(rawTotal) : null;
  return { items: data, total };
}

export function getMyComplaintApi(id: number, signal?: AbortSignal): Promise<ComplaintResponse> {
  return apiFetch<ComplaintResponse>(`/complaints/${id}`, { signal });
}

/** POST /complaints/duplicate-suggestions — TF-IDF similarity duplicate advisory check */
export async function getDuplicateSuggestionsApi(
  title: string,
  description: string,
  signal?: AbortSignal,
): Promise<DuplicateSuggestionsResponse> {
  try {
    return await apiFetch<DuplicateSuggestionsResponse>("/complaints/duplicate-suggestions", {
      method: "POST",
      body: { title: title.trim(), description: description.trim() },
      signal,
    });
  } catch (err) {
    if (signal?.aborted) throw err;
    // Resilient fallback: failure or 404/501 must never block student submission
    return { matches: [], disclaimer: "Duplicate suggestion service unavailable." };
  }
}

/** GET /complaints/{id}/history — Chronological status transition history */
export function getComplaintStatusHistoryApi(
  complaintId: number,
  signal?: AbortSignal,
): Promise<ComplaintStatusHistoryItem[]> {
  return apiFetch<ComplaintStatusHistoryItem[]>(`/complaints/${complaintId}/history`, { signal });
}

/** POST /complaints/{id}/reopen — Reopen a resolved complaint within allowed policy */
export function reopenComplaintApi(
  complaintId: number,
  payload?: ComplaintReopenPayload,
): Promise<ComplaintReopenResponse> {
  return apiFetch<ComplaintReopenResponse>(`/complaints/${complaintId}/reopen`, {
    method: "POST",
    body: payload?.remark ? { remark: payload.remark.trim() } : {},
  });
}
