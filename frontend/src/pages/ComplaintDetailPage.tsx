import React, { useCallback, useEffect, useState } from "react";
import { getMyComplaintApi, getComplaintStatusHistoryApi, reopenComplaintApi } from "../api/complaints";
import { ApiClientError, errorMessage } from "../api/client";
import { ComplaintResponse, ComplaintStatusHistoryItem } from "../types";
import {
  Alert,
  Button,
  ButtonLink,
  CopyButton,
  DetailList,
  EmptyState,
  Icon,
  Panel,
  Skeleton,
  StatusBadge,
  TextAreaField,
} from "../components/ui";
import { ComplaintStatusTimeline } from "../components/ComplaintStatusTimeline";
import { Link } from "../lib/router";
import { complaintReference, formatDateTime } from "../lib/format";
import { useDocumentTitle } from "../hooks/useMediaState";

export default function ComplaintDetailPage({ id }: { id: number }) {
  const reference = complaintReference(id);
  useDocumentTitle(reference);

  const [complaint, setComplaint] = useState<ComplaintResponse | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "not_found" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  // Status timeline state
  const [historyEvents, setHistoryEvents] = useState<ComplaintStatusHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // Reopen state
  const [showReopenForm, setShowReopenForm] = useState(false);
  const [reopenRemark, setReopenRemark] = useState("");
  const [reopening, setReopening] = useState(false);
  const [reopenError, setReopenError] = useState<string | null>(null);
  const [reopenSuccess, setReopenSuccess] = useState<string | null>(null);

  const loadComplaint = useCallback((signal?: AbortSignal) => {
    setState("loading");
    getMyComplaintApi(id, signal)
      .then((data) => {
        setComplaint(data);
        setState("ready");
      })
      .catch((err) => {
        if (signal?.aborted) return;
        if (err instanceof ApiClientError && err.status === 404) setState("not_found");
        else {
          setError(errorMessage(err));
          setState("error");
        }
      });
  }, [id]);

  const loadHistory = useCallback((signal?: AbortSignal) => {
    setHistoryLoading(true);
    setHistoryError(null);
    getComplaintStatusHistoryApi(id, signal)
      .then((events) => {
        setHistoryEvents(events || []);
      })
      .catch((err) => {
        if (signal?.aborted) return;
        setHistoryError(errorMessage(err, "Couldn't load status history."));
      })
      .finally(() => {
        setHistoryLoading(false);
      });
  }, [id]);

  useEffect(() => {
    const controller = new AbortController();
    loadComplaint(controller.signal);
    loadHistory(controller.signal);
    return () => controller.abort();
  }, [loadComplaint, loadHistory, reloadKey]);

  const handleReopen = async (e: React.FormEvent) => {
    e.preventDefault();
    if (reopening) return;
    setReopening(true);
    setReopenError(null);
    setReopenSuccess(null);

    try {
      await reopenComplaintApi(id, { remark: reopenRemark.trim() || undefined });
      setReopenSuccess("Complaint reopened successfully. Staff will review the issue again.");
      setShowReopenForm(false);
      setReopenRemark("");
      // Refresh both complaint details and history timeline
      setReloadKey((k) => k + 1);
    } catch (err) {
      setReopenError(errorMessage(err, "Failed to reopen complaint."));
    } finally {
      setReopening(false);
    }
  };

  const resolvedAt = complaint?.resolved_at
    ? Date.parse(complaint.resolved_at)
    : NaN;

  const now = Date.now();
  const reopenWindowMs = 7 * 24 * 60 * 60 * 1000;

  const isEligibleToReopen =
    complaint !== null &&
    complaint.status === "resolved" &&
    complaint.reopen_count !== undefined &&
    complaint.reopen_count < 2 &&
    Number.isFinite(resolvedAt) &&
    resolvedAt <= now &&
    now - resolvedAt <= reopenWindowMs;

  return (
    <div className="detail-page">
      <Link to="/complaints" className="back-link">
        <Icon name="arrowLeft" size={18} /> My complaints
      </Link>

      {state === "loading" ? (
        <Panel>
          <div className="row-skeleton" aria-busy="true" aria-label="Loading complaint">
            <Skeleton width="20%" height={14} />
            <Skeleton width="60%" height={26} />
            <Skeleton width="100%" height={80} />
          </div>
        </Panel>
      ) : state === "not_found" ? (
        <Panel>
          <EmptyState icon="search" title={`${reference} not found`} action={<ButtonLink to="/complaints">Back to my complaints</ButtonLink>}>
            There's no complaint with this reference in your history.
          </EmptyState>
        </Panel>
      ) : state === "error" ? (
        <Alert
          tone="error"
          title="Couldn't load this complaint"
          action={
            <Button size="sm" variant="secondary" icon="refresh" onClick={() => setReloadKey((k) => k + 1)}>
              Retry
            </Button>
          }
        >
          {error}
        </Alert>
      ) : complaint ? (
        <Panel as="article">
          <header className="detail-head">
            <div className="detail-head__ref">
              <span>{reference}</span>
              <CopyButton value={reference} label="Copy reference" />
            </div>
            <h1 className="detail-head__title">{complaint.title}</h1>
            <StatusBadge status={complaint.status} />
          </header>

          <section className="detail-section" aria-labelledby="desc-heading">
            <h2 id="desc-heading" className="detail-section__title">
              Description
            </h2>
            <p className="detail-description">{complaint.description}</p>
          </section>

          <section className="detail-section" aria-labelledby="info-heading">
            <h2 id="info-heading" className="detail-section__title">
              Details
            </h2>
            <DetailList
              items={[
                { label: "Department", value: complaint.department_name },
                { label: "Submitted", value: formatDateTime(complaint.created_at) },
                {
                  label: "Visibility",
                  value: complaint.is_public ? "Public (campus feed)" : "Private",
                },
                ...(complaint.location
                  ? [{ label: "Hostel location", value: `${complaint.location.hostel}, ${complaint.location.wing}, ${complaint.location.floor}` }]
                  : [
                      ...(complaint.hostel ? [{ label: "Hostel building", value: complaint.hostel }] : []),
                      ...(complaint.wing ? [{ label: "Wing / Block", value: complaint.wing }] : []),
                      ...(complaint.floor ? [{ label: "Floor", value: complaint.floor }] : []),
                    ]),
                ...(complaint.reopen_count ? [{ label: "Reopen count", value: String(complaint.reopen_count) }] : []),
                { label: "Current status", value: <StatusBadge status={complaint.status} /> },
              ]}
            />
          </section>

          {/* Conditional Reopen section for resolved complaints */}
          {reopenSuccess ? (
            <Alert tone="success" title="Reopened">
              {reopenSuccess}
            </Alert>
          ) : null}

          {isEligibleToReopen ? (
            <div className="reopen-box" role="region" aria-label="Reopen complaint">
              <div className="reopen-box__head">
                <span className="reopen-box__icon" aria-hidden="true">
                  <Icon name="refresh" size={20} />
                </span>
                <div>
                  <h3 className="reopen-box__title">Is this issue still not resolved?</h3>
                  <p className="reopen-box__text">
                    You can reopen this complaint if the resolution was incomplete or the issue recurred.
                  </p>
                </div>
              </div>

              {reopenError ? (
                <Alert tone="error" title="Couldn't reopen">
                  {reopenError}
                </Alert>
              ) : null}

              {!showReopenForm ? (
                <Button
                  variant="secondary"
                  size="sm"
                  icon="refresh"
                  onClick={() => setShowReopenForm(true)}
                >
                  Reopen complaint
                </Button>
              ) : (
                <form onSubmit={handleReopen} className="reopen-box__form">
                  <TextAreaField
                    label="Reason for reopening (optional)"
                    name="remark"
                    placeholder="Describe why this issue needs further attention..."
                    value={reopenRemark}
                    onChange={(e) => setReopenRemark(e.target.value)}
                    maxLength={2000}
                    rows={3}
                    disabled={reopening}
                    hint="Optional explanation up to 2000 characters."
                  />
                  <div className="reopen-box__actions">
                    <Button
                      type="submit"
                      variant="primary"
                      size="sm"
                      loading={reopening}
                      disabled={reopening}
                    >
                      {reopening ? "Reopening…" : "Confirm reopen"}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setShowReopenForm(false);
                        setReopenRemark("");
                        setReopenError(null);
                      }}
                      disabled={reopening}
                    >
                      Cancel
                    </Button>
                  </div>
                </form>
              )}
            </div>
          ) : null}

          {/* Status History Timeline */}
          <section className="detail-section detail-section--timeline" aria-labelledby="timeline-heading">
            <h2 id="timeline-heading" className="detail-section__title">
              Status History
            </h2>
            <ComplaintStatusTimeline
              events={historyEvents}
              loading={historyLoading}
              error={historyError}
              onRetry={() => loadHistory()}
            />
          </section>
        </Panel>
      ) : null}
    </div>
  );
}
