import { useCallback, useEffect, useRef, useState } from 'react';

import { useAuth } from '../context/AuthContext';
import { getDepartmentsApi } from '../api/departments';
import { getHostelLocationsApi } from '../api/locations';
import { ApiClientError, errorMessage } from '../api/client';

import {
  getStaffComplaintsApi,
  getStaffComplaintApi,
  getComplaintHistoryApi,
  updateStaffComplaintStatusApi,
  getStaffResidencesApi,
  decideStaffResidenceApi,
  type StaffComplaintQueueItem,
  type StaffComplaintDetail,
  type ComplaintStatusHistoryItem,
  type StaffComplaintStatus,
  type StaffResidenceItem,
  type ResidenceStatus,
} from '../api/staff';

import type { Department, HostelNode } from '../types';

import {
  Alert,
  Button,
  PageHeader,
  Panel,
  Skeleton,
} from '../components/ui';

import { firstName } from '../lib/format';
import { useDocumentTitle } from '../hooks/useMediaState';

type ComplaintFilter = 'all' | StaffComplaintStatus;

const PAGE_SIZE = 20;

const complaintFilters: { label: string; value: ComplaintFilter }[] = [
  { label: 'All complaints', value: 'all' },
  { label: 'Submitted', value: 'submitted' },
  { label: 'In progress', value: 'in_progress' },
  { label: 'Resolved', value: 'resolved' },
  { label: 'Reopened', value: 'reopened' },
];

const residenceFilters: { label: string; value: ResidenceStatus }[] = [
  { label: 'Pending verification', value: 'pending' },
  { label: 'Verified', value: 'verified' },
  { label: 'Rejected', value: 'rejected' },
];

function readableStatus(status: string) {
  return status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function readableDate(value: string | null | undefined) {
  if (!value) return '—';

  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function queueLocation(complaint: StaffComplaintQueueItem) {
  return (
    [complaint.hostel, complaint.wing, complaint.floor]
      .filter(Boolean)
      .join(', ') || '—'
  );
}

export default function StaffDashboard() {
  useDocumentTitle('Staff dashboard');

  const { user } = useAuth();
  const complaintRequestId = useRef(0);
  const detailRequestId = useRef(0);

  // Department information
  const [department, setDepartment] = useState<Department | null>(null);

  // Sprint 2: complaint queue
  const [complaintFilter, setComplaintFilter] =
    useState<ComplaintFilter>('all');
  const [complaintPage, setComplaintPage] = useState(0);
  // Sprint 3 S3-24: hostel filter (Hostel staff only)
  const [hostels, setHostels] = useState<HostelNode[]>([]);
  const [hostelFilter, setHostelFilter] = useState<number | null>(null);
  const [complaints, setComplaints] = useState<StaffComplaintQueueItem[]>([]);
  const [complaintTotal, setComplaintTotal] = useState<number | null>(null);
  const [complaintLoading, setComplaintLoading] = useState(true);
  const [complaintError, setComplaintError] = useState<string | null>(null);

  // Sprint 2: complaint detail and status history
  const [selectedComplaintId, setSelectedComplaintId] =
    useState<number | null>(null);
  const [complaintDetail, setComplaintDetail] =
    useState<StaffComplaintDetail | null>(null);
  const [complaintDetailLoading, setComplaintDetailLoading] = useState(false);
  const [complaintDetailError, setComplaintDetailError] =
    useState<string | null>(null);
  const [history, setHistory] = useState<ComplaintStatusHistoryItem[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [nextStatus, setNextStatus] =
    useState<'in_progress' | 'resolved'>('in_progress');
  const [complaintRemark, setComplaintRemark] = useState('');
  const [complaintSaving, setComplaintSaving] = useState(false);
  const [complaintActionMessage, setComplaintActionMessage] =
    useState<string | null>(null);
  const [complaintActionError, setComplaintActionError] =
    useState<string | null>(null);

  // Sprint 3 S3-23: residence verification queue
  const [residenceStatus, setResidenceStatus] =
    useState<ResidenceStatus>('pending');
  const [residencePage, setResidencePage] = useState(0);
  const [residences, setResidences] = useState<StaffResidenceItem[]>([]);
  const [residenceTotal, setResidenceTotal] = useState<number | null>(null);
  const [residenceLoading, setResidenceLoading] = useState(false);
  const [residenceError, setResidenceError] = useState<string | null>(null);
  const [residenceRemarks, setResidenceRemarks] = useState<
    Record<number, string>
  >({});
  const [residenceSavingId, setResidenceSavingId] = useState<number | null>(
    null,
  );
  const [residenceActionError, setResidenceActionError] =
    useState<string | null>(null);
  const [residenceMessage, setResidenceMessage] = useState<string | null>(null);

  // Matches the backend rule: only Hostel-department staff may review residences.
  // The hostel filter and queue location are shown to the same staff.
  const isHostelStaff =
    user?.role === 'staff' &&
    department?.name.trim().toLowerCase() === 'hostel';

  // Load the staff member's department label.
  useEffect(() => {
    if (!user) return;

    const controller = new AbortController();

    getDepartmentsApi(controller.signal)
      .then((departments) => {
        if (controller.signal.aborted) return;

        setDepartment(
          user.department_id
            ? departments.find((item) => item.id === user.department_id) ??
                null
            : null,
        );
      })
      .catch(() => {
        // The dashboard remains usable if department labels cannot be loaded.
      });

    return () => controller.abort();
  }, [user?.department_id]);

  // Load hostel options for the queue filter.
  useEffect(() => {
    if (!isHostelStaff) return;

    const controller = new AbortController();

    getHostelLocationsApi(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) setHostels(items);
      })
      .catch(() => {
        // The queue remains usable with only "All hostels".
      });

    return () => controller.abort();
  }, [isHostelStaff]);

  // Load complaint queue.
  const loadComplaints = useCallback(
    async (signal?: AbortSignal) => {
      const requestId = ++complaintRequestId.current;

      setComplaintLoading(true);
      setComplaintError(null);

      try {
        const result = await getStaffComplaintsApi(
          {
            status:
              complaintFilter === 'all' ? undefined : complaintFilter,
            hostel_id: hostelFilter ?? undefined,
            limit: PAGE_SIZE,
            offset: complaintPage * PAGE_SIZE,
          },
          signal,
        );

        // Ignore stale or cancelled requests.
        if (
          signal?.aborted ||
          requestId !== complaintRequestId.current
        ) {
          return;
        }

        setComplaints(result.items);
        setComplaintTotal(result.total);
      } catch (error) {
        if (
          signal?.aborted ||
          requestId !== complaintRequestId.current
        ) {
          return;
        }

        setComplaintError(errorMessage(error));
      } finally {
        if (
          !signal?.aborted &&
          requestId === complaintRequestId.current
        ) {
          setComplaintLoading(false);
        }
      }
    },
    [complaintFilter, hostelFilter, complaintPage],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadComplaints(controller.signal);

    return () => controller.abort();
  }, [loadComplaints]);

  // Load Sprint 3 residence queue.
  const loadResidences = useCallback(
    async (signal?: AbortSignal) => {
      if (!isHostelStaff) return;

      setResidenceLoading(true);
      setResidenceError(null);

      try {
        const result = await getStaffResidencesApi(
          {
            status: residenceStatus,
            limit: PAGE_SIZE,
            offset: residencePage * PAGE_SIZE,
          },
          signal,
        );

        if (signal?.aborted) return;

        setResidences(result.items);
        setResidenceTotal(result.total);
      } catch (error) {
        if (signal?.aborted) return;
        setResidenceError(errorMessage(error));
      } finally {
        if (!signal?.aborted) setResidenceLoading(false);
      }
    },
    [isHostelStaff, residenceStatus, residencePage],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadResidences(controller.signal);

    return () => controller.abort();
  }, [loadResidences]);

  // Open a complaint and retrieve its status history.
  async function openComplaint(id: number) {
    const requestId = ++detailRequestId.current;

    setSelectedComplaintId(id);
    setComplaintDetail(null);
    setHistory([]);
    setHistoryError(null);
    setComplaintDetailError(null);
    setComplaintActionError(null);
    setComplaintActionMessage(null);
    setComplaintRemark('');
    setComplaintDetailLoading(true);

    try {
      const detail = await getStaffComplaintApi(id);

      // Ignore a response if another complaint was selected afterward.
      if (requestId !== detailRequestId.current) return;

      setComplaintDetail(detail);
      setNextStatus(
        detail.status === 'in_progress' ? 'resolved' : 'in_progress',
      );

      try {
        const events = await getComplaintHistoryApi(id);

        if (requestId !== detailRequestId.current) return;

        setHistory(events);
      } catch (error) {
        if (requestId !== detailRequestId.current) return;

        setHistoryError(errorMessage(error));
      }
    } catch (error) {
      if (requestId !== detailRequestId.current) return;

      setComplaintDetailError(errorMessage(error));
    } finally {
      // Only the most recent request may stop the loading indicator.
      if (requestId === detailRequestId.current) {
        setComplaintDetailLoading(false);
      }
    }
  }

  // Update complaint status.
  async function submitComplaintStatus() {
    if (!complaintDetail || !complaintRemark.trim()) {
      setComplaintActionError('Please enter a remark before updating status.');
      return;
    }

    setComplaintSaving(true);
    setComplaintActionError(null);
    setComplaintActionMessage(null);

    try {
      const updated = await updateStaffComplaintStatusApi(
        complaintDetail.id,
        nextStatus,
        complaintRemark.trim(),
      );

      setComplaintDetail(updated);
      setNextStatus(
        updated.status === 'in_progress' ? 'resolved' : 'in_progress',
      );
      setComplaintRemark('');
      setComplaintActionMessage('Complaint status updated successfully.');

      await loadComplaints();

      try {
        const events = await getComplaintHistoryApi(updated.id);
        setHistory(events);
        setHistoryError(null);
      } catch (error) {
        setHistoryError(errorMessage(error));
      }
    } catch (error) {
      if (error instanceof ApiClientError && error.status === 501) {
        setComplaintActionError(
          'Status updates are not available yet because the backend service is not ready.',
        );
      } else {
        setComplaintActionError(errorMessage(error));
      }
    } finally {
      setComplaintSaving(false);
    }
  }

  // Sprint 3 S3-23: approve or reject a residence declaration.
  async function submitResidenceDecision(
    residence: StaffResidenceItem,
    decision: 'approve' | 'reject',
  ) {
    const trimmedRemark = (residenceRemarks[residence.id] ?? '').trim();

    if (decision === 'reject' && !trimmedRemark) {
      setResidenceActionError(
        'A remark is required when rejecting a residence declaration.',
      );
      return;
    }

    if (trimmedRemark.length > 2000) {
      setResidenceActionError('The remark must be 2000 characters or fewer.');
      return;
    }

    setResidenceSavingId(residence.id);
    setResidenceActionError(null);
    setResidenceMessage(null);

    try {
      await decideStaffResidenceApi(residence.id, {
        decision,
        ...(trimmedRemark ? { remark: trimmedRemark } : {}),
      });

      setResidenceMessage(
        `Residence declaration for ${residence.student_name} ${
          decision === 'approve' ? 'approved' : 'rejected'
        }.`,
      );

      setResidenceRemarks((prev) => ({ ...prev, [residence.id]: '' }));
      await loadResidences();
    } catch (error) {
      if (error instanceof ApiClientError && error.status === 409) {
        setResidenceActionError(
          'This residence request has already been decided. Refresh the queue.',
        );
      } else {
        setResidenceActionError(errorMessage(error));
      }
    } finally {
      setResidenceSavingId(null);
    }
  }

  if (!user) return null;

  return (
    <div>
      <PageHeader
        title={`Hello, ${firstName(user.name) || 'colleague'}`}
        description="Manage complaints and review student residence declarations."
      />

      <div className="staff-grid">
        <Panel title="Your staff account">
          <p>
            <strong>Name:</strong> {user.name}
          </p>
          <p>
            <strong>Email:</strong> {user.email}
          </p>
          <p>
            <strong>Department:</strong>{' '}
            {department?.name ??
              (user.department_id
                ? `Department #${user.department_id}`
                : 'No department assigned')}
          </p>
          <p>
            <strong>Role:</strong> {readableStatus(user.role)}
          </p>
        </Panel>

        {/* Sprint 2: Department complaint queue */}
        <Panel title="Department complaint queue">
          <div className="staff-filter-row">
            <label htmlFor="complaint-filter">Filter by status</label>

            <select
              id="complaint-filter"
              value={complaintFilter}
              onChange={(event) => {
                setComplaintFilter(event.target.value as ComplaintFilter);
                setComplaintPage(0);
              }}
            >
              {complaintFilters.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>

            {isHostelStaff && (
              <>
                <label htmlFor="hostel-filter">Filter by hostel</label>

                <select
                  id="hostel-filter"
                  value={hostelFilter ?? ''}
                  onChange={(event) => {
                    setHostelFilter(
                      event.target.value ? Number(event.target.value) : null,
                    );
                    setComplaintPage(0);
                  }}
                >
                  <option value="">All hostels</option>
                  {hostels.map((hostel) => (
                    <option key={hostel.id} value={hostel.id}>
                      {hostel.name}
                    </option>
                  ))}
                </select>
              </>
            )}

            <Button
              size="sm"
              variant="secondary"
              icon="refresh"
              disabled={complaintLoading}
              onClick={() => void loadComplaints()}
            >
              Refresh
            </Button>
          </div>

          {complaintLoading ? (
            <div aria-label="Loading complaints">
              <Skeleton height={22} />
              <Skeleton height={22} />
              <Skeleton height={22} />
            </div>
          ) : complaintError ? (
            <Alert tone="error" title="Couldn't load complaints">
              {complaintError}
              <div className="mt-4">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void loadComplaints()}
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
                {complaintTotal === null
                  ? `${complaints.length} complaint(s) loaded`
                  : `${complaintTotal} complaint(s) found`}
              </p>

              <div className="staff-complaint-list">
                {complaints.map((complaint) => (
                  <button
                    type="button"
                    key={complaint.id}
                    className={`staff-complaint-item ${
                      selectedComplaintId === complaint.id ? 'is-selected' : ''
                    }`}
                    onClick={() => void openComplaint(complaint.id)}
                  >
                    <span className="staff-complaint-heading">
                      <strong>
                        #{complaint.id} — {complaint.title}
                      </strong>
                      <span
                        className={`staff-status status-${complaint.status}`}
                      >
                        {readableStatus(complaint.status)}
                      </span>
                    </span>

                    <span>{complaint.description_preview}</span>

                    {isHostelStaff && (
                      <span className="staff-complaint-location">
                        <strong>Location:</strong> {queueLocation(complaint)}
                      </span>
                    )}

                    <small>
                      Submitted: {readableDate(complaint.created_at)}
                    </small>

                    {complaint.status === 'reopened' && (
                      <strong className="staff-reopened">
                        Reopened complaint
                      </strong>
                    )}
                  </button>
                ))}
              </div>

              {complaintTotal !== null && complaintTotal > PAGE_SIZE && (
                <div
                  className="staff-filter-row"
                  aria-label="Complaint pagination"
                >
                  <span>
                    Page {complaintPage + 1} of{' '}
                    {Math.ceil(complaintTotal / PAGE_SIZE)}
                  </span>

                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={complaintPage === 0 || complaintLoading}
                    onClick={() =>
                      setComplaintPage((page) => Math.max(0, page - 1))
                    }
                  >
                    Previous
                  </Button>

                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={
                      complaintLoading ||
                      (complaintPage + 1) * PAGE_SIZE >= complaintTotal
                    }
                    onClick={() => setComplaintPage((page) => page + 1)}
                  >
                    Next
                  </Button>
                </div>
              )}
            </>
          )}
        </Panel>

        {/* Sprint 2: Complaint details */}
        <Panel title="Complaint details">
          {selectedComplaintId === null ? (
            <p className="muted-note">
              Select a complaint from the queue to view its details.
            </p>
          ) : complaintDetailLoading ? (
            <div aria-label="Loading complaint details">
              <Skeleton height={24} />
              <Skeleton height={24} />
              <Skeleton height={24} />
            </div>
          ) : complaintDetailError ? (
            <Alert tone="error" title="Couldn't load complaint">
              {complaintDetailError}
              <div className="mt-4">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void openComplaint(selectedComplaintId)}
                >
                  Try again
                </Button>
              </div>
            </Alert>
          ) : complaintDetail ? (
            <div className="staff-detail">
              <h3>
                #{complaintDetail.id} — {complaintDetail.title}
              </h3>

              {complaintDetail.status === 'reopened' && (
                <Alert tone="info" title="Reopened complaint">
                  This complaint has been reopened. Review its details before
                  taking action.
                </Alert>
              )}

              <p>
                <strong>Department:</strong> {complaintDetail.department_name}
              </p>
              <p>
                <strong>Status:</strong>{' '}
                {readableStatus(complaintDetail.status)}
              </p>
              <p>
                <strong>Description:</strong>
              </p>
              <p>{complaintDetail.description}</p>
              <p>
                <strong>Submitted:</strong>{' '}
                {readableDate(complaintDetail.created_at)}
              </p>
              <p>
                <strong>Last updated:</strong>{' '}
                {readableDate(complaintDetail.updated_at)}
              </p>

              {(complaintDetail.hostel ||
                complaintDetail.wing ||
                complaintDetail.floor) && (
                <p>
                  <strong>Location:</strong>{' '}
                  {[
                    complaintDetail.hostel,
                    complaintDetail.wing,
                    complaintDetail.floor,
                  ]
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

              {complaintDetail.status === 'resolved' ? (
                <p className="muted-note">
                  This complaint is resolved. Reopening is handled separately.
                </p>
              ) : (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    void submitComplaintStatus();
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
                    {complaintDetail.status === 'in_progress' ? (
                      <option value="resolved">Resolved</option>
                    ) : (
                      <option value="in_progress">In progress</option>
                    )}
                  </select>

                  <label htmlFor="complaint-remark">
                    Remark (required)
                  </label>
                  <textarea
                    id="complaint-remark"
                    value={complaintRemark}
                    onChange={(event) =>
                      setComplaintRemark(event.target.value)
                    }
                    maxLength={2000}
                    required
                    rows={4}
                    placeholder="Explain the action taken or resolution..."
                  />

                  {complaintActionError && (
                    <Alert tone="error">{complaintActionError}</Alert>
                  )}

                  {complaintActionMessage && (
                    <Alert tone="info">{complaintActionMessage}</Alert>
                  )}

                  <Button
                    type="submit"
                    disabled={complaintSaving || !complaintRemark.trim()}
                    loading={complaintSaving}
                  >
                    Save status update
                  </Button>
                </form>
              )}
            </div>
          ) : null}
        </Panel>
      </div>

      {/* Sprint 3 S3-23: Residence verification */}
      {isHostelStaff && (
        <div className="staff-residence-section">
          <Panel title="Residence verification queue">
            <p className="muted-note">
              Review student residence declarations. Approve correct
              declarations or reject them with a reason.
            </p>

            <div className="staff-filter-row">
              <label htmlFor="residence-status-filter">
                Filter residence requests by status
              </label>

              <select
                id="residence-status-filter"
                value={residenceStatus}
                onChange={(event) => {
                  setResidenceStatus(event.target.value as ResidenceStatus);
                  setResidencePage(0);
                  setResidenceMessage(null);
                  setResidenceActionError(null);
                }}
              >
                {residenceFilters.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>

              <Button
                size="sm"
                variant="secondary"
                icon="refresh"
                disabled={residenceLoading}
                onClick={() => void loadResidences()}
              >
                Refresh
              </Button>
            </div>

            {residenceMessage && (
              <Alert tone="info" title="Decision submitted">
                {residenceMessage}
              </Alert>
            )}

            {residenceActionError && (
              <Alert tone="error" title="Could not submit decision">
                {residenceActionError}
              </Alert>
            )}

            {residenceLoading ? (
              <div aria-label="Loading residence requests">
                <Skeleton height={22} />
                <Skeleton height={22} />
                <Skeleton height={22} />
              </div>
            ) : residenceError ? (
              <Alert tone="error" title="Couldn't load residence requests">
                {residenceError}
                <div className="mt-4">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => void loadResidences()}
                  >
                    Try again
                  </Button>
                </div>
              </Alert>
            ) : residences.length === 0 ? (
              <p className="muted-note">
                No residence declarations found for this status.
              </p>
            ) : (
              <>
                <p className="muted-note">
                  {residenceTotal === null
                    ? `${residences.length} declaration(s) loaded`
                    : `${residenceTotal} declaration(s) found`}
                </p>

                <div className="staff-residence-list">
                  {residences.map((residence) => (
                    <article
                      className="staff-residence-item"
                      key={residence.id}
                    >
                      <div className="staff-residence-heading">
                        <h3>
                          {residence.student_name || 'Student'} — Residence
                          declaration #{residence.id}
                        </h3>
                        <span
                          className={`staff-status status-${residence.status}`}
                        >
                          {readableStatus(residence.status)}
                        </span>
                      </div>

                      <p>
                        <strong>Student ID:</strong> {residence.student_id}
                      </p>
                      <p>
                        <strong>Email:</strong> {residence.student_email}
                      </p>
                      <p>
                        <strong>Hostel:</strong> {residence.hostel}
                      </p>
                      <p>
                        <strong>Wing:</strong> {residence.wing}
                      </p>
                      <p>
                        <strong>Floor:</strong> {residence.floor}
                      </p>
                      <p>
                        <strong>Submitted:</strong>{' '}
                        {readableDate(residence.submitted_at)}
                      </p>

                      {residence.decided_at && (
                        <p>
                          <strong>Decision date:</strong>{' '}
                          {readableDate(residence.decided_at)}
                        </p>
                      )}

                      {residence.remark && (
                        <p>
                          <strong>Previous remark:</strong> {residence.remark}
                        </p>
                      )}

                      {residence.status === 'pending' ? (
                        <>
                          <label htmlFor={`residence-remark-${residence.id}`}>
                            Remark
                            {residence.status === 'pending'
                              ? ' (required for rejection)'
                              : ''}
                          </label>

                          <textarea
                            id={`residence-remark-${residence.id}`}
                            rows={3}
                            maxLength={2000}
                            value={residenceRemarks[residence.id] ?? ''}
                            onChange={(event) => {
                              const { value } = event.target;
                              setResidenceRemarks((prev) => ({
                                ...prev,
                                [residence.id]: value,
                              }));
                              setResidenceActionError(null);
                            }}
                            placeholder="Explain the reason if rejecting..."
                            disabled={residenceSavingId !== null}
                          />

                          <div className="staff-filter-row">
                            <Button
                              size="sm"
                              disabled={residenceSavingId !== null}
                              loading={residenceSavingId === residence.id}
                              onClick={() =>
                                void submitResidenceDecision(
                                  residence,
                                  'approve',
                                )
                              }
                            >
                              Approve residence
                            </Button>

                            <Button
                              size="sm"
                              variant="secondary"
                              disabled={residenceSavingId !== null}
                              loading={residenceSavingId === residence.id}
                              onClick={() =>
                                void submitResidenceDecision(
                                  residence,
                                  'reject',
                                )
                              }
                            >
                              Reject residence
                            </Button>
                          </div>
                        </>
                      ) : (
                        <p className="muted-note">
                          This declaration has already been{' '}
                          {residence.status}. No further decision is available.
                        </p>
                      )}
                    </article>
                  ))}
                </div>

                {residenceTotal !== null &&
                  residenceTotal > PAGE_SIZE && (
                    <div
                      className="staff-filter-row"
                      aria-label="Residence pagination"
                    >
                      <span>
                        Page {residencePage + 1} of{' '}
                        {Math.ceil(residenceTotal / PAGE_SIZE)}
                      </span>

                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={residencePage === 0 || residenceLoading}
                        onClick={() =>
                          setResidencePage((page) => Math.max(0, page - 1))
                        }
                      >
                        Previous
                      </Button>

                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={
                          residenceLoading ||
                          (residencePage + 1) * PAGE_SIZE >= residenceTotal
                        }
                        onClick={() => setResidencePage((page) => page + 1)}
                      >
                        Next
                      </Button>
                    </div>
                  )}
              </>
            )}
          </Panel>
        </div>
      )}
    </div>
  );
}
