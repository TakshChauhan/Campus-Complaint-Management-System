import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { getDepartmentsApi } from '../api/departments';
import { getHostelLocationsApi } from '../api/locations';
import { getDepartmentFeedApi, getHostelFeedApi } from '../api/feeds';
import { errorMessage } from '../api/client';
import { Department, FeedItem, HostelFeedItem, HostelNode } from '../types';
import { Alert, Button, EmptyState, Icon, PageHeader, Panel, Skeleton, StatusBadge } from '../components/ui';
import { complaintReference, formatDate } from '../lib/format';
import { useDocumentTitle } from '../hooks/useMediaState';
import './pages.css';

const PAGE_SIZE = 10;
const MAX_LIMIT = 100;

export default function CampusFeedPage() {
  useDocumentTitle('Campus Public Feed');
  const { user } = useAuth();
  const isStaffOrAdmin = user?.role === 'staff' || user?.role === 'admin';

  // Reference data
  const [departments, setDepartments] = useState<Department[]>([]);
  const [locations, setLocations] = useState<HostelNode[]>([]);
  const [metaLoading, setMetaLoading] = useState(true);

  // Filter state
  const [selectedDeptId, setSelectedDeptId] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [selectedScope, setSelectedScope] = useState<'hostel' | 'wing' | 'floor'>('hostel');
  const [selectedHostelId, setSelectedHostelId] = useState<string>('all');

  // Pagination state
  const [page, setPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [totalCount, setTotalCount] = useState<number>(0);

  // Feed items & query state
  const [feedItems, setFeedItems] = useState<(FeedItem | HostelFeedItem)[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [hostelFeedNotice, setHostelFeedNotice] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState<number>(0);
  const [limitNotice, setLimitNotice] = useState<string | null>(null);

  const requestIdRef = useRef<number>(0);

  // Load departments and location hierarchy once
  useEffect(() => {
    const controller = new AbortController();
    setMetaLoading(true);

    Promise.allSettled([
      getDepartmentsApi(controller.signal),
      getHostelLocationsApi(controller.signal),
    ])
      .then(([deptRes, locRes]) => {
        if (controller.signal.aborted) return;
        if (deptRes.status === 'fulfilled') setDepartments(deptRes.value);
        if (locRes.status === 'fulfilled') setLocations(locRes.value);
      })
      .finally(() => {
        if (!controller.signal.aborted) setMetaLoading(false);
      });

    return () => controller.abort();
  }, []);

  // Determine if a department is the Hostel department
  const isHostelDepartment = useCallback(
    (dept: Department) => dept.name.trim().toLowerCase() === 'hostel',
    [],
  );

  // Load feed items whenever filters, scope, page, or reloadKey change
  useEffect(() => {
    if (metaLoading) return;

    const currentReqId = ++requestIdRef.current;
    const controller = new AbortController();
    setLoading(true);
    setFeedItems([]);
    setError(null);
    setHostelFeedNotice(null);
    setLimitNotice(null);

    const statusParam = selectedStatus !== 'all' ? selectedStatus : undefined;
    const numericHostelId = isStaffOrAdmin && selectedHostelId !== 'all' ? Number(selectedHostelId) : undefined;
    const scopeParam = isStaffOrAdmin ? undefined : selectedScope;

    async function fetchFeed() {
      try {
        if (selectedDeptId !== 'all') {
          // Scenario 1: Specific department
          const dept = departments.find((d) => String(d.id) === selectedDeptId);
          if (dept && isHostelDepartment(dept)) {
            try {
              const res = await getHostelFeedApi({
                scope: scopeParam,
                hostelId: numericHostelId,
                status: statusParam,
                limit: PAGE_SIZE,
                offset: (page - 1) * PAGE_SIZE,
                signal: controller.signal,
              });
              if (controller.signal.aborted || currentReqId !== requestIdRef.current) return;
              setFeedItems(res.items);
              setTotalCount(res.total);
              setTotalPages(Math.max(1, Math.ceil(res.total / PAGE_SIZE)));
            } catch (err: unknown) {
              if (controller.signal.aborted || currentReqId !== requestIdRef.current) return;
              const raw = (err as { rawDetail?: unknown })?.rawDetail as Record<string, unknown> | undefined;
              const code = (raw?.detail as Record<string, unknown> | undefined)?.code ?? raw?.code;
              if (code === 'residence_not_verified') {
                setHostelFeedNotice('Hostel complaints require a verified student residence.');
                setFeedItems([]);
                setTotalCount(0);
                setTotalPages(1);
              } else {
                throw err;
              }
            }
          } else {
            const res = await getDepartmentFeedApi(Number(selectedDeptId), {
              status: statusParam,
              limit: PAGE_SIZE,
              offset: (page - 1) * PAGE_SIZE,
              signal: controller.signal,
            });
            if (controller.signal.aborted || currentReqId !== requestIdRef.current) return;
            setFeedItems(res.items);
            setTotalCount(res.total);
            setTotalPages(Math.max(1, Math.ceil(res.total / PAGE_SIZE)));
          }
        } else {
          // Scenario 2: All Departments
          const activeDepts = departments.filter((d) => d.is_active !== false);
          const nonHostelDepts = activeDepts.filter((d) => !isHostelDepartment(d));
          const hasHostelDept = activeDepts.some((d) => isHostelDepartment(d));

          const fetchLimit = page * PAGE_SIZE;
          if (fetchLimit > MAX_LIMIT) {
            setLimitNotice(
              `Page size multiplied by page number (${fetchLimit}) exceeds source limit cap (${MAX_LIMIT}). Further items cannot be retrieved.`
            );
          }

          const cappedLimit = Math.min(fetchLimit, MAX_LIMIT);

          const deptPromises = nonHostelDepts.map(async (d) => {
            try {
              const res = await getDepartmentFeedApi(d.id, {
                status: statusParam,
                limit: cappedLimit,
                offset: 0,
                signal: controller.signal,
              });
              return { ok: true as const, items: res.items, total: res.total };
            } catch (err) {
              return { ok: false as const, error: err, items: [], total: 0 };
            }
          });

          let hostelItems: HostelFeedItem[] = [];
          let hostelTotal = 0;
          if (hasHostelDept || departments.length === 0) {
            try {
              const hostelRes = await getHostelFeedApi({
                scope: scopeParam,
                hostelId: numericHostelId,
                status: statusParam,
                limit: cappedLimit,
                offset: 0,
                signal: controller.signal,
              });
              hostelItems = hostelRes.items;
              hostelTotal = hostelRes.total;
            } catch (err: unknown) {
              const raw = (err as { rawDetail?: unknown })?.rawDetail as Record<string, unknown> | undefined;
              const code = (raw?.detail as Record<string, unknown> | undefined)?.code ?? raw?.code;
              const status = (err as { status?: number }).status;
              if (code === 'residence_not_verified') {
                setHostelFeedNotice('Hostel complaints require a verified student residence.');
              } else if (status === 401) {
                setHostelFeedNotice('Authentication required to view hostel complaints.');
              } else if (status === 403) {
                setHostelFeedNotice('Hostel complaints are restricted for your account.');
              } else {
                throw err;
              }
            }
          }

          const deptResults = await Promise.all(deptPromises);
          if (controller.signal.aborted || currentReqId !== requestIdRef.current) return;

          const firstFailure = deptResults.find((r) => !r.ok);
          if (firstFailure && !firstFailure.ok) {
            throw firstFailure.error;
          }

          const allDeptItems = deptResults.flatMap((r) => r.items);
          const allItems = [...hostelItems, ...allDeptItems];

          // Deduplicate by complaint ID
          const seenIds = new Set<number>();
          const deduped: (FeedItem | HostelFeedItem)[] = [];
          let duplicateCount = 0;
          for (const item of allItems) {
            if (seenIds.has(item.id)) {
              duplicateCount++;
            } else {
              seenIds.add(item.id);
              deduped.push(item);
            }
          }

          // Sort descending by created_at, then id
          deduped.sort((a, b) => {
            const timeA = new Date(a.created_at).getTime();
            const timeB = new Date(b.created_at).getTime();
            if (timeA !== timeB) return timeB - timeA;
            return b.id - a.id;
          });

          const sumTotals = hostelTotal + deptResults.reduce((acc, r) => acc + (r.total ?? 0), 0);
          // Note: totalAvailable is the sum of source totals minus duplicates observed
          // within the fetched window. It is exact only when no duplicate complaint IDs exist
          // beyond the fetched window.
          const totalAvailable = Math.max(deduped.length, sumTotals - duplicateCount);
          const totalPagesCount = Math.max(1, Math.ceil(totalAvailable / PAGE_SIZE));

          const startIndex = (page - 1) * PAGE_SIZE;
          const pageItems = deduped.slice(startIndex, startIndex + PAGE_SIZE);

          setFeedItems(pageItems);
          setTotalCount(totalAvailable);
          setTotalPages(totalPagesCount);
        }
      } catch (err) {
        if (controller.signal.aborted || currentReqId !== requestIdRef.current) return;
        setError(errorMessage(err, 'Failed to load public complaints feed.'));
      } finally {
        if (!controller.signal.aborted && currentReqId === requestIdRef.current) {
          setLoading(false);
        }
      }
    }

    fetchFeed();

    return () => controller.abort();
  }, [
    selectedDeptId,
    selectedStatus,
    selectedScope,
    selectedHostelId,
    page,
    reloadKey,
    departments,
    metaLoading,
    isHostelDepartment,
    isStaffOrAdmin,
  ]);

  const handleDeptChange = (deptId: string) => {
    setSelectedDeptId(deptId);
    setPage(1);
  };

  const handleStatusChange = (status: string) => {
    setSelectedStatus(status);
    setPage(1);
  };

  const handleScopeChange = (scope: 'hostel' | 'wing' | 'floor') => {
    setSelectedScope(scope);
    setPage(1);
  };

  const handleHostelChange = (hostelId: string) => {
    setSelectedHostelId(hostelId);
    setPage(1);
  };

  const resetFilters = () => {
    setSelectedDeptId('all');
    setSelectedStatus('all');
    setSelectedScope('hostel');
    setSelectedHostelId('all');
    setPage(1);
  };

  const isFilterActive =
    selectedDeptId !== 'all' ||
    selectedStatus !== 'all' ||
    (!isStaffOrAdmin && selectedScope !== 'hostel') ||
    (isStaffOrAdmin && selectedHostelId !== 'all');

  return (
    <div>
      <PageHeader
        title="Campus Public Feed"
        description="Browse published complaints across campus departments and hostels. Student identities are strictly protected."
        actions={
          <Button
            variant="secondary"
            icon="refresh"
            onClick={() => setReloadKey((k) => k + 1)}
            aria-label="Refresh public feed"
          >
            Refresh
          </Button>
        }
      />

      {/* Privacy Protection Banner */}
      <div className="feed-privacy-banner" role="status">
        <Icon name="shield" size={18} />
        <div>
          <strong>Student Privacy Guaranteed:</strong> Personal identifiers (names, email addresses, and roll numbers) are never exposed on public feeds.
        </div>
      </div>

      {/* Filter and Control Toolbar */}
      <section className="feed-toolbar" aria-label="Feed filters">
        <div className="feed-filter-grid">
          {/* Department Filter */}
          <div className="feed-filter-group">
            <label htmlFor="feed-department-filter">Department</label>
            <select
              id="feed-department-filter"
              value={selectedDeptId}
              onChange={(e) => handleDeptChange(e.target.value)}
              disabled={loading && metaLoading}
            >
              <option value="all">All Departments</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>

          {/* Status Filter */}
          <div className="feed-filter-group">
            <label htmlFor="feed-status-filter">Status</label>
            <select
              id="feed-status-filter"
              value={selectedStatus}
              onChange={(e) => handleStatusChange(e.target.value)}
              disabled={loading && metaLoading}
            >
              <option value="all">All Statuses</option>
              <option value="submitted">Submitted</option>
              <option value="in_progress">In Progress</option>
              <option value="resolved">Resolved</option>
              <option value="reopened">Reopened</option>
            </select>
          </div>

          {/* Student Scope Selector */}
          {!isStaffOrAdmin && (
            <div className="feed-filter-group" role="radiogroup" aria-label="Hostel feed scope">
              <label id="feed-scope-label">Scope</label>
              <div className="feed-scope-options" style={{ display: 'flex', gap: 'var(--space-2)' }}>
                {(['hostel', 'wing', 'floor'] as const).map((sc) => {
                  const label = sc === 'hostel' ? 'Hostel' : sc === 'wing' ? 'My Wing' : 'My Floor';
                  return (
                    <label
                      key={sc}
                      className={`btn btn--sm ${selectedScope === sc ? 'btn--primary' : 'btn--secondary'}`}
                      style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center' }}
                    >
                      <input
                        type="radio"
                        name="feedScope"
                        value={sc}
                        checked={selectedScope === sc}
                        onChange={() => handleScopeChange(sc)}
                        style={{ position: 'absolute', opacity: 0, width: 0, height: 0 }}
                        aria-label={label}
                      />
                      {label}
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          {/* Staff and Admin Hostel Selector */}
          {isStaffOrAdmin && (
            <div className="feed-filter-group">
              <label htmlFor="feed-hostel-filter">Hostel</label>
              <select
                id="feed-hostel-filter"
                aria-label="Hostel"
                value={selectedHostelId}
                onChange={(e) => handleHostelChange(e.target.value)}
                disabled={loading && metaLoading}
              >
                <option value="all">All Hostels</option>
                {locations.map((h) => (
                  <option key={h.id} value={String(h.id)}>
                    {h.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Toolbar Actions & Summary */}
        <div className="feed-toolbar__actions">
          <span className="feed-count-summary">
            {loading ? (
              'Loading complaints...'
            ) : (
              `Showing ${feedItems.length} public complaint${feedItems.length === 1 ? '' : 's'}`
            )}
          </span>
          {isFilterActive && (
            <Button variant="ghost" size="sm" onClick={resetFilters}>
              Clear all filters
            </Button>
          )}
        </div>
      </section>

      {/* Notice Alert if any */}
      {hostelFeedNotice && (
        <Alert tone="info" className="mb-4">
          {hostelFeedNotice}
        </Alert>
      )}

      {/* Limit Notice Alert if any */}
      {limitNotice && (
        <Alert tone="warning" className="mb-4">
          {limitNotice}
        </Alert>
      )}

      {/* Error Alert with Retry */}
      {error && (
        <Alert tone="error">
          <div className="flex items-center justify-between">
            <span>{error}</span>
            <Button variant="secondary" size="sm" onClick={() => setReloadKey((k) => k + 1)}>
              Retry
            </Button>
          </div>
        </Alert>
      )}

      {/* Main Content Area */}
      {loading ? (
        <div className="feed-list" aria-busy="true">
          {[1, 2, 3].map((n) => (
            <div key={n} className="feed-card">
              <div className="feed-card__header">
                <Skeleton width={120} height={22} />
                <Skeleton width={80} height={22} />
              </div>
              <Skeleton width="75%" height={26} />
              <Skeleton width={160} height={20} />
              <div className="feed-card__footer">
                <Skeleton width={100} height={16} />
                <Skeleton width={60} height={16} />
              </div>
            </div>
          ))}
        </div>
      ) : feedItems.length === 0 ? (
        limitNotice ? null : (
          <Panel>
            <EmptyState
              icon="inbox"
              title={isFilterActive ? 'No matching public complaints' : 'No public complaints published yet'}
              action={
                isFilterActive ? (
                  <Button variant="secondary" onClick={resetFilters}>
                    Clear all filters
                  </Button>
                ) : undefined
              }
            >
              <p>
                {isFilterActive
                  ? 'Try adjusting or clearing your filters to see more complaints.'
                  : 'When complaints are published by campus departments or verified hostels, they will appear here.'}
              </p>
            </EmptyState>
          </Panel>
        )
      ) : (
        <div className="feed-list" role="feed" aria-label="Campus public complaints">
          {feedItems.map((item) => {
            const hasLocation = Boolean(item.hostel || item.wing || item.floor);
            const locationParts = [item.hostel, item.wing, item.floor].filter(Boolean);

            return (
              <article key={item.id} className="feed-card" aria-labelledby={`complaint-title-${item.id}`}>
                <div className="feed-card__header">
                  <div className="feed-card__meta-left">
                    <span className="feed-card__dept-badge">{item.department_name}</span>
                    <StatusBadge status={item.status} />
                    {item.reopen_count > 0 && (
                      <span className="feed-card__reopen-badge" title={`Reopened ${item.reopen_count} time(s)`}>
                        Reopened {item.reopen_count}x
                      </span>
                    )}
                  </div>
                </div>

                <h2 id={`complaint-title-${item.id}`} className="feed-card__title">
                  {item.title}
                </h2>

                {hasLocation && (
                  <div className="feed-card__location">
                    <Icon name="building" size={14} />
                    <span>{locationParts.join(' • ')}</span>
                  </div>
                )}

                <div className="feed-card__footer">
                  <time dateTime={item.created_at}>{formatDate(item.created_at)}</time>
                  <span className="feed-card__ref">{complaintReference(item.id)}</span>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {/* Pagination Controls */}
      {!error && (totalPages > 1 || page > 1 || feedItems.length > 0) && (
        <nav className="pagination" aria-label="Campus feed pagination">
          <Button
            variant="secondary"
            size="sm"
            icon="chevronLeft"
            disabled={page <= 1 || loading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Previous
          </Button>
          <span className="pagination__status">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="secondary"
            size="sm"
            iconAfter="chevronRight"
            disabled={page >= totalPages || page * PAGE_SIZE > MAX_LIMIT || loading}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </nav>
      )}
    </div>
  );
}
