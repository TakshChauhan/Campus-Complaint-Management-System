
import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { getDepartmentsApi } from '../api/departments';
import { ApiClientError, errorMessage } from '../api/client';
import {
  getStaffComplaintsApi,
  getStaffComplaintApi,
  getComplaintHistoryApi,
  updateStaffComplaintStatusApi,
  type StaffComplaintQueueItem,
  type StaffComplaintDetail,
  type ComplaintStatusHistoryItem,
  type StaffComplaintStatus,
} from '../api/staff';
import type { Department } from '../types';
import {
  Alert,
  Button,
  PageHeader,
  Panel,
  Skeleton,
} from '../components/ui';
import { firstName } from '../lib/format';
import { useDocumentTitle } from '../hooks/useMediaState';

type FilterStatus = 'all' | StaffComplaintStatus;

const PAGE_SIZE = 20;

const filters: { label: string; value: FilterStatus }[] = [
  { label: 'All complaints', value: 'all' },
  { label: 'Submitted', value: 'submitted' },
  { label: 'In progress', value: 'in_progress' },
  { label: 'Resolved', value: 'resolved' },
  { label: 'Reopened', value: 'reopened' },
];

function readableStatus(status: string) {
  return status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function readableDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function StaffDashboard() {
  useDocumentTitle('Staff dashboard');

  const { user } = useAuth();

  const [department, setDepartment] = useState<Department | null>(null);
  const [filter, setFilter] = useState<FilterStatus>('all');
  const [page, setPage] = useState(0);

  const [complaints, setComplaints] = useState<StaffComplaintQueueItem[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [queueLoading, setQueueLoading] = useState(true);
  const [queueError, setQueueError] = useState<string | null>(null);

  const detailRequestId = useRef(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<StaffComplaintDetail | null>(null);
  const [history, setHistory] = useState<ComplaintStatusHistoryItem[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [nextStatus, setNextStatus] = useState<'in_progress' | 'resolved'>(
    'in_progress',
  );
  const [remark, setRemark] = useState('');
  const [saving, setSaving] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadQueue = useCallback(
    async (signal?: AbortSignal) => {
      setQueueLoading(true);
      setQueueError(null);

      try {
        const result = await getStaffComplaintsApi(
          {
            status: filter === 'all' ? undefined : filter,
            limit: PAGE_SIZE,
            offset: page * PAGE_SIZE,
          },
          signal,
        );

        if (signal?.aborted) return;

        setComplaints(result.items);
        setTotal(result.total);
      } catch (error) {
        if (signal?.aborted) return;
        setQueueError(errorMessage(error));
      } finally {
        if (!signal?.aborted) setQueueLoading(false);
      }
    },
    [filter, page],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadQueue(controller.signal);
    return () => controller.abort();
  }, [loadQueue]);

  useEffect(() => {
    const controller = new AbortController();

    getDepartmentsApi(controller.signal)
      .then((departments) => {
        if (controller.signal.aborted) return;
        setDepartment(
          user?.department_id
            ? departments.find((item) => item.id === user.department_id) ?? null
            : null,
        );
      })
      .catch(() => {
        // The complaint queue remains usable if department labels fail to load.
      });

    return () => controller.abort();
  }, [user?.department_id]);

  const openComplaint = useCallback(async (id: number) => {
    const requestId = ++detailRequestId.current;
    const isCurrent = () => requestId === detailRequestId.current;

    setSelectedId(id);
    setDetail(null);
    setHistory([]);
    setHistoryError(null);
    setDetailError(null);
    setActionError(null);
    setActionMessage(null);
    setRemark('');
    setDetailLoading(true);

    try {
      const complaint = await getStaffComplaintApi(id);
      if (!isCurrent()) return;

      setDetail(complaint);
      setNextStatus(
        complaint.status === 'in_progress' ? 'resolved' : 'in_progress',
      );

      try {
        const events = await getComplaintHistoryApi(id);
        if (!isCurrent()) return;
        setHistory(events);
      } catch (error) {
        if (isCurrent()) setHistoryError(errorMessage(error));
      }
    } catch (error) {
      if (isCurrent()) setDetailError(errorMessage(error));
    } finally {
      if (isCurrent()) setDetailLoading(false);
    }
  }, []);

  async function submitStatusUpdate() {
    if (!detail || !remark.trim()) {
      setActionError('Please enter a remark before updating the status.');
      return;
    }

    setSaving(true);
    setActionError(null);
    setActionMessage(null);

    try {
      const updated = await updateStaffComplaintStatusApi(
        detail.id,
        nextStatus,
        remark.trim(),
      );

      setDetail(updated);
      setNextStatus(
        updated.status === 'in_progress' ? 'resolved' : 'in_progress',
      );
      setRemark('');
      setActionMessage('Complaint status updated successfully.');

      await loadQueue();

      // Refresh the history to show the latest status change.
      try {
        const events = await getComplaintHistoryApi(updated.id);
        setHistory(events);
      } catch (error) {
        setHistoryError(errorMessage(error));
      }
    } catch (error) {
      if (error instanceof ApiClientError && error.status === 501){
        setActionError(
          'Status updates are not available yet because the backend service is not ready.'
        );
      } else{
        setActionError(errorMessage(error));
      }
    } finally {
      setSaving(false);
    }
  }

  if (!user) return null;

  return (
    <div>
      <PageHeader
        title={`Hello, ${firstName(user.name) || 'colleague'}`}
        description="Manage complaints assigned to your department."
      />

      <div className="staff-grid">
        <Panel title="Your staff account">
          <p><strong>Name:</strong> {user.name}</p>
          <p><strong>Email:</strong> {user.email}</p>
          <p>
            <strong>Department:</strong>{' '}
            {department?.name ??
              (user.department_id
                ? `Department #${user.department_id}`
                : 'No department assigned')}
          </p>
        </Panel>

        <Panel title="Department complaint queue">
          <div className="staff-filter-row">
            <label htmlFor="complaint-filter">
              Filter by status
            </label>
            <select
              id="complaint-filter"
              value={filter}
              onChange={(event) => {
                setFilter(event.target.value as FilterStatus);
                setPage(0);
              }}
            >
              {filters.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>

            <Button
              size="sm"
              variant="secondary"
              icon="refresh"
              onClick={() => void loadQueue()}
              disabled={queueLoading}
            >
              Refresh
            </Button>
          </div>

          {queueLoading ? (
            <div aria-label="Loading complaints">
              <Skeleton height={22} />
              <Skeleton height={22} />
              <Skeleton height={22} />
            </div>
          ) : queueError ? (
            <Alert tone="error" title="Couldn't load complaints">
              {queueError}
              <div className="mt-4">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void loadQueue()}
                >
                  Try again
                </Button>
              </div>
            </Alert>
          ) : complaints.length === 0 ? (
            <p className="muted-note">
              No complaints found for this filter.
            </p>
          ) : (
            <>
              <p className="muted-note">
                {total === null
                  ? `${complaints.length} complaint(s) loaded`
                  : `${total} complaint(s) found`}
              </p>

              <div className="staff-complaint-list">
                {complaints.map((complaint) => (
                  <button
                    type="button"
                    key={complaint.id}
                    className={`staff-complaint-item ${
                      selectedId === complaint.id ? 'is-selected' : ''
                    }`}
                    onClick={() => void openComplaint(complaint.id)}
                  >
                    <span className="staff-complaint-heading">
                      <strong>#{complaint.id} — {complaint.title}</strong>
                      <span className={`staff-status status-${complaint.status}`}>
                        {readableStatus(complaint.status)}
                      </span>
                    </span>

                    <span>{complaint.description_preview}</span>
                    <small>Submitted: {readableDate(complaint.created_at)}</small>
                    {complaint.status === 'reopened' && (
                      <strong className="staff-reopened">
                        Reopened complaint
                      </strong>
                    )}
                  </button>
                ))}
              </div>
              {total !== null && total > PAGE_SIZE && (
                <div className="staff-filter-row" aria-label="Complaint pagination">
                  <span>Page {page + 1} of {Math.ceil(total / PAGE_SIZE)}</span>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={page === 0 || queueLoading}
                    onClick={() => setPage(p => Math.max(0, p - 1))}
                  >
                    Previous
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={queueLoading || (page + 1) * PAGE_SIZE >= total}
                    onClick={() => setPage(p => p + 1)}
                  >
                    Next
                  </Button>
                </div>
              )}
            </>
          )}
        </Panel>

        <Panel title="Complaint details">
          {selectedId === null ? (
            <p className="muted-note">
              Select a complaint from the queue to view its details.
            </p>
          ) : detailLoading ? (
            <div aria-label="Loading complaint details">
              <Skeleton height={24} />
              <Skeleton height={24} />
              <Skeleton height={24} />
            </div>
          ) : detailError ? (
            <Alert tone="error" title="Couldn't load complaint">
              {detailError}
              <div className="mt-4">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void openComplaint(selectedId)}
                >
                  Try again
                </Button>
              </div>
            </Alert>
          ) : detail ? (
            <div className="staff-detail">
              <h3>#{detail.id} — {detail.title}</h3>

              {detail.status === 'reopened' && (
                <Alert tone="info" title="Reopened complaint">
                  This complaint has been reopened. Review its details before
                  taking action.
                </Alert>
              )}

              <p><strong>Department:</strong> {detail.department_name}</p>
              <p><strong>Status:</strong> {readableStatus(detail.status)}</p>
              <p><strong>Description:</strong></p>
              <p>{detail.description}</p>
              <p><strong>Submitted:</strong> {readableDate(detail.created_at)}</p>
              <p><strong>Last updated:</strong> {readableDate(detail.updated_at)}</p>

              {(detail.hostel || detail.wing || detail.floor) && (
                <p>
                  <strong>Location:</strong>{' '}
                  {[detail.hostel, detail.wing, detail.floor]
                    .filter(Boolean)
                    .join(', ')}
                </p>
              )}

              <hr />

              <h3>Status history</h3>

              {historyError ? (
                <p role="alert" className="muted-note">
                  Couldn't load status history: {historyError}
                </p>
              ) : history.length === 0 ? (
                <p className="muted-note">
                  No status history is available.
                </p>
              ) : (
                <ol className="staff-history">
                  {history.map((event) => (
                    <li key={event.id}>
                      <strong>{readableStatus(event.to_status)}</strong>
                      <small>{readableDate(event.created_at)}</small>
                      {event.remark && <p>{event.remark}</p>}
                    </li>
                  ))}
                </ol>
              )}

              <hr />

              <h3>Update complaint status</h3>

              {detail.status === 'resolved' ? (
                <p className="muted-note">
                  This complaint is resolved. Reopening is handled separately.
                </p>
              ) : (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    void submitStatusUpdate();
                  }}
                >
                  <label htmlFor="next-status">New status</label>
                  <select
                    id="next-status"
                    value={nextStatus}
                    onChange={(event) =>
                      setNextStatus(
                        event.target.value as 'in_progress' | 'resolved',
                      )
                    }
                  >
                    {detail.status === 'in_progress' ? (
                      <option value="resolved">Resolved</option>
                    ) : (
                      <option value="in_progress">In progress</option>
                    )}
                  </select>

                  <label htmlFor="status-remark">Remark (required)</label>
                  <textarea
                    id="status-remark"
                    value={remark}
                    onChange={(event) => setRemark(event.target.value)}
                    minLength={1}
                    maxLength={2000}
                    required
                    rows={4}
                    placeholder="Explain the action taken or resolution..."
                  />

                  {actionError && (
                    <Alert tone="error">{actionError}</Alert>
                  )}
                  {actionMessage && (
                    <Alert tone="info">{actionMessage}</Alert>
                  )}

                  <Button
                    type="submit"
                    disabled={saving || !remark.trim()}
                    loading={saving}
                  >
                    Save status update
                  </Button>
                </form>
              )}
            </div>
          ) : null}
        </Panel>
      </div>
    </div>
  );
}
