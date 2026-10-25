import React from "react";
import { ComplaintStatusHistoryItem } from "../types";
import { Alert, Button, Icon, Skeleton, StatusBadge } from "./ui";
import { formatDateTime } from "../lib/format";

interface ComplaintStatusTimelineProps {
  events: ComplaintStatusHistoryItem[];
  loading: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export function ComplaintStatusTimeline({
  events,
  loading,
  error,
  onRetry,
}: ComplaintStatusTimelineProps) {
  if (loading) {
    return (
      <div className="status-timeline status-timeline--loading" aria-busy="true" aria-label="Loading timeline">
        <Skeleton width="40%" height={16} />
        <div style={{ marginTop: 12 }}>
          <Skeleton width="100%" height={48} />
        </div>
        <div style={{ marginTop: 12 }}>
          <Skeleton width="100%" height={48} />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <Alert
        tone="error"
        title="Couldn't load status history"
        action={
          onRetry ? (
            <Button size="sm" variant="secondary" icon="refresh" onClick={onRetry}>
              Retry
            </Button>
          ) : undefined
        }
      >
        {error}
      </Alert>
    );
  }

  if (!events || events.length === 0) {
    return (
      <div className="status-timeline--empty">
        <p className="status-timeline__empty-text">
          No status change events recorded yet. The current status is shown above.
        </p>
      </div>
    );
  }

  // Ensure chronological ordering: created_at ASC, id ASC
  const sortedEvents = [...events].sort((a, b) => {
    const timeA = new Date(a.created_at).getTime();
    const timeB = new Date(b.created_at).getTime();
    if (timeA !== timeB) return timeA - timeB;
    return a.id - b.id;
  });

  return (
    <div className="status-timeline" role="region" aria-label="Complaint status history timeline">
      <ol className="timeline-list">
        {sortedEvents.map((event, index) => {
          const isLatest = index === sortedEvents.length - 1;
          return (
            <li key={event.id} className={`timeline-item ${isLatest ? "timeline-item--latest" : ""}`}>
              <div className="timeline-item__indicator" aria-hidden="true">
                <span className="timeline-item__dot" />
                {index < sortedEvents.length - 1 ? <span className="timeline-item__line" /> : null}
              </div>

              <div className="timeline-item__content">
                <div className="timeline-item__header">
                  <div className="timeline-item__status-change">
                    {event.from_status ? (
                      <>
                        <StatusBadge status={event.from_status} />
                        <span className="timeline-item__arrow" aria-hidden="true">
                          <Icon name="chevronRight" size={14} />
                        </span>
                      </>
                    ) : null}
                    <StatusBadge status={event.to_status} />
                  </div>
                  <time className="timeline-item__time" dateTime={event.created_at}>
                    {formatDateTime(event.created_at)}
                  </time>
                </div>

                {event.remark ? (
                  <blockquote className="timeline-item__remark">
                    "{event.remark}"
                  </blockquote>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
