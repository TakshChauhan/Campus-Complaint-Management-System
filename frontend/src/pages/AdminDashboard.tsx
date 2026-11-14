import React, { ReactNode, useCallback, useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { getHealthApi, getReadinessApi } from '../api/system';
import { getDepartmentsApi } from '../api/departments';
import { getAdminMetricsSummaryApi, getAdminStaffApi, updateStaffHostelsApi } from '../api/admin';
import { getHostelLocationsApi } from '../api/locations';
import { errorMessage } from '../api/client';
import { AdminMetricsSummary, AdminStaffListItem, Department, HealthResponse, HostelNode, ReadinessResponse } from '../types';
import { Alert, Button, DetailList, PageHeader, Panel, Skeleton, StatusBadge } from '../components/ui';
import { useDocumentTitle } from '../hooks/useMediaState';

type Load<T> = { state: 'loading' } | { state: 'ok'; data: T; checkedAt: Date } | { state: 'error'; message: string };

function Indicator({ tone, children }: { tone: 'ok' | 'bad' | 'unknown'; children: ReactNode }) {
  return (
    <span className={`indicator indicator--${tone}`}>
      <span className="indicator__dot" aria-hidden="true" />
      {children}
    </span>
  );
}

export default function AdminDashboard() {
  useDocumentTitle('System & Complaint Metrics');
  const { user } = useAuth();
  const [health, setHealth] = useState<Load<HealthResponse>>({ state: 'loading' });
  const [ready, setReady] = useState<Load<ReadinessResponse>>({ state: 'loading' });
  const [departments, setDepartments] = useState<Load<Department[]>>({ state: 'loading' });
  const [metrics, setMetrics] = useState<Load<AdminMetricsSummary>>({ state: 'loading' });
  const [staff, setStaff] = useState<Load<AdminStaffListItem[]>>({ state: 'loading' });
  const [hostels, setHostels] = useState<Load<HostelNode[]>>({ state: 'loading' });
  const [savingStaffId, setSavingStaffId] = useState<number | null>(null);
  const [assignmentError, setAssignmentError] = useState<string | null>(null);
  const [assignmentSuccess, setAssignmentSuccess] = useState<string | null>(null);
  const [selectedHostels, setSelectedHostels] = useState<Record<number, number[]>>({});

  const load = useCallback((signal?: AbortSignal) => {
    setHealth({ state: 'loading' });
    setReady({ state: 'loading' });
    setDepartments({ state: 'loading' });
    setMetrics({ state: 'loading' });
    setStaff({ state: 'loading' });
    setHostels({ state: 'loading' });

    const settle = <T,>(p: Promise<T>, set: (v: Load<T>) => void) =>
      p
        .then((data) => set({ state: 'ok', data, checkedAt: new Date() }))
        .catch((err) => {
          if (!signal?.aborted) set({ state: 'error', message: errorMessage(err) });
        });

    settle(getHealthApi(signal), setHealth);
    settle(getReadinessApi(signal), setReady);
    settle(getDepartmentsApi(signal), setDepartments);
    settle(getAdminMetricsSummaryApi(signal), setMetrics);
    settle(getAdminStaffApi(signal), setStaff);
    settle(getHostelLocationsApi(signal), setHostels);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const handleSaveHostels = async (member: AdminStaffListItem) => {
    setSavingStaffId(member.id);
    setAssignmentError(null);
    setAssignmentSuccess(null);

    const hostelIds =
      selectedHostels[member.id] ?? member.hostels.map((hostel) => hostel.id);

    try {
      await updateStaffHostelsApi(member.id, { hostel_ids: hostelIds });
    } catch (error) {
      setAssignmentError(errorMessage(error));
      setSavingStaffId(null);
      return;
    }

    setSelectedHostels((previous) => {
      const next = { ...previous };
      delete next[member.id];
      return next;
    });

    setAssignmentSuccess(`Hostel assignments updated for ${member.name}.`);

    try {
      const refreshedStaff = await getAdminStaffApi();
      setStaff({ state: 'ok', data: refreshedStaff, checkedAt: new Date() });
    } catch {
      setAssignmentError(
        'Assignments were saved, but the staff list could not be refreshed. Reload the page to see the latest assignments.'
      );
    } finally {
      setSavingStaffId(null);
    }
  };
  const apiValue =
    health.state === 'loading' ? (
      <Skeleton width={120} />
    ) : health.state === 'error' ? (
      <Indicator tone="bad">Unreachable</Indicator>
    ) : health.data.status === 'healthy' ? (
      <Indicator tone="ok">Healthy</Indicator>
    ) : (
      <Indicator tone="bad">Degraded</Indicator>
    );

  const dbValue =
    ready.state === 'loading' ? (
      <Skeleton width={120} />
    ) : ready.state === 'error' ? (
      <Indicator tone="unknown">Unknown (API unreachable)</Indicator>
    ) : ready.data.ready ? (
      <Indicator tone="ok">Ready</Indicator>
    ) : (
      <Indicator tone="bad">Not reachable</Indicator>
    );

  const checkedAt = health.state === 'ok' ? health.checkedAt : null;

  // Extract status counts
  const statusCountsMap: Record<string, number> = {};
  if (metrics.state === 'ok') {
    for (const item of metrics.data.status_counts) {
      statusCountsMap[item.status.toLowerCase()] = item.count;
    }
  }

  const countFor = (statusKey: string) => {
    if (metrics.state === 'loading') return <Skeleton width={40} height={28} />;
    if (metrics.state === 'error') return '—';
    return statusCountsMap[statusKey] ?? 0;
  };

  const totalComplaintsCount = () => {
    if (metrics.state === 'loading') return <Skeleton width={50} height={28} />;
    if (metrics.state === 'error') return '—';
    return metrics.data.total_complaints;
  };

  // Resolution metrics
  const resolutionData = metrics.state === 'ok' ? metrics.data.resolution_metrics : null;

  const averageHoursDisplay = () => {
    if (metrics.state === 'loading') return <Skeleton width={140} height={42} />;
    if (!resolutionData || resolutionData.average_resolution_hours === null) return '—';
    return `${resolutionData.average_resolution_hours.toFixed(1)} hrs`;
  };

  const averageDaysSubtext = () => {
    if (!resolutionData || resolutionData.average_resolution_days === null) return null;
    return `(~${resolutionData.average_resolution_days.toFixed(1)} days)`;
  };

  return (
    <div>
      <PageHeader
        title="Admin Metrics & System Overview"
        description="Campus complaint statistics, resolution performance metrics, and CCMS backend status."
        actions={
          <Button variant="secondary" icon="refresh" onClick={() => load()}>
            Check again
          </Button>
        }
      />

      {metrics.state === 'error' ? (
        <Alert tone="error" className="mb-6">
          Could not load complaint metrics: {metrics.message}
        </Alert>
      ) : null}

      {/* Complaint Counts by Status */}
      <section aria-labelledby="status-metrics-heading">
        <h2 id="status-metrics-heading" className="visually-hidden">
          Complaint Statistics by Status
        </h2>
        <div className="metrics-summary-grid">
          <div className="metric-stat-card" data-testid="stat-total">
            <div className="metric-stat-card__head">
              <span className="metric-stat-card__label">Total Complaints</span>
            </div>
            <div className="metric-stat-card__value">{totalComplaintsCount()}</div>
            <span className="metric-stat-card__desc">Across all departments</span>
          </div>

          <div className="metric-stat-card" data-testid="stat-submitted">
            <div className="metric-stat-card__head">
              <span className="metric-stat-card__label">Submitted</span>
              <StatusBadge status="submitted" />
            </div>
            <div className="metric-stat-card__value">{countFor('submitted')}</div>
            <span className="metric-stat-card__desc">Awaiting staff pickup</span>
          </div>

          <div className="metric-stat-card" data-testid="stat-in-progress">
            <div className="metric-stat-card__head">
              <span className="metric-stat-card__label">In Progress</span>
              <StatusBadge status="in_progress" />
            </div>
            <div className="metric-stat-card__value">{countFor('in_progress')}</div>
            <span className="metric-stat-card__desc">Being actively handled</span>
          </div>

          <div className="metric-stat-card" data-testid="stat-resolved">
            <div className="metric-stat-card__head">
              <span className="metric-stat-card__label">Resolved</span>
              <StatusBadge status="resolved" />
            </div>
            <div className="metric-stat-card__value">{countFor('resolved')}</div>
            <span className="metric-stat-card__desc">Successfully addressed</span>
          </div>

          <div className="metric-stat-card" data-testid="stat-reopened">
            <div className="metric-stat-card__head">
              <span className="metric-stat-card__label">Reopened</span>
              <StatusBadge status="reopened" />
            </div>
            <div className="metric-stat-card__value">{countFor('reopened')}</div>
            <span className="metric-stat-card__desc">Student requested review</span>
          </div>
        </div>
      </section>

      {/* Performance & Department Distribution */}
      <div className="metrics-perf-grid">
        {/* Rolling-average resolution time */}
        <Panel title="Resolution Performance (Rolling 30 Days)">
          <div className="metric-highlight">
            <span className="metric-highlight__val">{averageHoursDisplay()}</span>
            <span className="metric-highlight__unit">{averageDaysSubtext()}</span>
          </div>

          {metrics.state === 'loading' ? (
            <div className="row-skeletons">
              <Skeleton height={18} width="80%" />
              <Skeleton height={18} width="60%" />
              <Skeleton height={18} width="70%" />
            </div>
          ) : (
            <DetailList
              items={[
                {
                  label: 'Rolling window',
                  value: `${resolutionData?.window_days ?? 30} days`,
                },
                {
                  label: 'Resolved in window',
                  value: `${resolutionData?.resolved_count ?? 0} complaints`,
                },
                {
                  label: 'Median resolution time',
                  value:
                    resolutionData?.median_resolution_hours !== null && resolutionData?.median_resolution_hours !== undefined
                      ? `${resolutionData.median_resolution_hours.toFixed(1)} hrs`
                      : '—',
                },
                {
                  label: 'Fastest resolution (min)',
                  value:
                    resolutionData?.min_resolution_hours !== null && resolutionData?.min_resolution_hours !== undefined
                      ? `${resolutionData.min_resolution_hours.toFixed(1)} hrs`
                      : '—',
                },
                {
                  label: 'Longest resolution (max)',
                  value:
                    resolutionData?.max_resolution_hours !== null && resolutionData?.max_resolution_hours !== undefined
                      ? `${resolutionData.max_resolution_hours.toFixed(1)} hrs`
                      : '—',
                },
              ]}
            />
          )}

          {/* Definition displayed on screen as required by specification */}
          <div className="metric-definition-box" role="region" aria-label="Metric definition">
            <p className="metric-definition-box__title">Rolling-Average Resolution Time Definition</p>
            <p className="metric-definition-box__text">
              The rolling-average resolution time is the mean of (resolved_at − created_at), in hours, calculated across all
              complaints resolved within the last 30 days. For complaints reopened within allowed policy windows, duration
              is measured from initial submission to final resolution.
            </p>
          </div>
        </Panel>

        {/* Complaints by Department */}
        <Panel
          title={
            departments.state === 'ok'
              ? `Active departments (${departments.data.length})`
              : 'Active departments'
          }
        >
          {departments.state === 'loading' || metrics.state === 'loading' ? (
            <div className="row-skeletons">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} height={18} width={`${60 + ((i * 13) % 30)}%`} />
              ))}
            </div>
          ) : departments.state === 'error' ? (
            <Alert tone="error">Departments couldn't be loaded: {departments.message}</Alert>
          ) : departments.data.length === 0 ? (
            <p className="muted-note">No active departments available.</p>
          ) : (
            <table className="dept-table" aria-label="Department-wise complaint counts">
              <thead>
                <tr>
                  <th scope="col">Department</th>
                  <th scope="col">Scope</th>
                  <th scope="col" style={{ textAlign: 'right' }}>
                    Complaints
                  </th>
                </tr>
              </thead>
              <tbody>
                {departments.data.map((d) => {
                  const deptCount =
                    metrics.state === 'error'
                      ? '—'
                      : metrics.state === 'ok'
                      ? metrics.data.department_counts.find((dc) => dc.department_id === d.id)?.count ?? 0
                      : '—';
                  return (
                    <tr key={d.id}>
                      <th scope="row">{d.name}</th>
                      <td>{d.description || 'No description'}</td>
                      <td style={{ textAlign: 'right' }}>
                        <span className="dept-count-badge">{deptCount}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      {/* Staff Hostel Assignments */}
      <section className="mb-6" aria-label="Staff hostel assignments">
        <Panel title="Staff Hostel Assignments">
          <div className="space-y-4">
            <p className="muted-note">
              View staff members and manage the hostels assigned to each member.
            </p>

            {assignmentError ? (
              <Alert tone="error">{assignmentError}</Alert>
            ) : null}

            {assignmentSuccess ? (
              <p role="status" className="text-sm">
                {assignmentSuccess}
              </p>
            ) : null}

            {staff.state === 'loading' ? (
              <div className="row-skeletons">
                <Skeleton height={24} width="55%" />
                <Skeleton height={18} width="80%" />
                <Skeleton height={18} width="65%" />
              </div>
            ) : staff.state === 'error' ? (
              <Alert tone="error">
                Could not load staff members: {staff.message}
              </Alert>
            ) : staff.data.length === 0 ? (
              <p className="muted-note">No staff members found.</p>
            ) : hostels.state === 'loading' ? (
              <Skeleton height={60} width="100%" />
            ) : hostels.state === 'error' ? (
              <Alert tone="error">
                Could not load hostel locations: {hostels.message}
              </Alert>
            ) : hostels.data.length === 0 ? (
              <p className="muted-note">No active hostels are available.</p>
            ) : (
              <div className="space-y-4">
                {staff.data.map((member) => {
                  const selectedIds =
                    selectedHostels[member.id] ??
                    member.hostels.map((hostel) => hostel.id);

                  return (
                    <article
                      key={member.id}
                      className="panel-card"
                      aria-label={`Hostel assignments for ${member.name}`}
                    >
                      <div className="mb-3">
                        <h3>{member.name}</h3>
                        <p className="muted-note">{member.email}</p>
                        <p className="muted-note">
                          Department: {member.department_name ?? 'Not assigned'}
                        </p>
                        <p className="muted-note">
                          Currently assigned:{' '}
                          {member.hostels.length > 0
                            ? member.hostels.map((hostel) => hostel.name).join(', ')
                            : 'No hostels'}
                        </p>
                      </div>

                      <fieldset className="mb-3">
                        <legend className="font-medium mb-2">
                          Assign hostels
                        </legend>

                        <div className="flex flex-wrap gap-3">
                          {hostels.data.map((hostel) => (
                            <label
                              key={hostel.id}
                              className="flex items-center gap-2"
                            >
                              <input
                                type="checkbox"
                                aria-label={`Assign ${hostel.name} to ${member.name}`}
                                checked={selectedIds.includes(hostel.id)}
                                onChange={(event) => {
                                  const checked = event.target.checked;

                                  setSelectedHostels((previous) => {
                                    const current =
                                      previous[member.id] ??
                                      member.hostels.map((item) => item.id);

                                    const next = checked
                                      ? [...current, hostel.id]
                                      : current.filter((id) => id !== hostel.id);

                                    return {
                                      ...previous,
                                      [member.id]: next,
                                    };
                                  });
                                }}
                              />
                              <span>{hostel.name}</span>
                            </label>
                          ))}
                        </div>
                      </fieldset>

                      <Button
                        onClick={() => handleSaveHostels(member)}
                        disabled={savingStaffId !== null}
                        loading={savingStaffId === member.id}
                      >
                        Save assignments
                      </Button>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        </Panel>
      </section>
      {/* Backend Health & Admin Profile (Sprint 1) */}
      <div className="admin-grid">
        <Panel title="Service status">
          <DetailList
            items={[
              { label: 'API', value: apiValue },
              { label: 'Database', value: dbValue },
              { label: 'Version', value: health.state === 'ok' ? health.data.version : '—' },
              { label: 'Environment', value: health.state === 'ok' ? health.data.environment : '—' },
              {
                label: 'Last checked',
                value: checkedAt
                  ? checkedAt.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', second: '2-digit' })
                  : '—',
              },
            ]}
          />
          {health.state === 'error' ? (
            <Alert tone="error" className="mt-4">
              The health endpoint did not respond: {health.message}
            </Alert>
          ) : null}
        </Panel>

        <Panel title="Administrator">
          <DetailList
            items={[
              { label: 'Name', value: user?.name ?? '' },
              { label: 'Email', value: user?.email ?? '' },
            ]}
          />
        </Panel>
      </div>
    </div>
  );
}
