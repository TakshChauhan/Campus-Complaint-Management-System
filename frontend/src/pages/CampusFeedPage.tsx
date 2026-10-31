import React, { useCallback, useEffect, useMemo, useState } from 'react';
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

export default function CampusFeedPage() {
  useDocumentTitle('Campus Public Feed');
  const { user } = useAuth();

  // Reference data
  const [departments, setDepartments] = useState<Department[]>([]);
  const [locations, setLocations] = useState<HostelNode[]>([]);
  const [metaLoading, setMetaLoading] = useState(true);

  // Filter state
  const [selectedDeptId, setSelectedDeptId] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [selectedHostel, setSelectedHostel] = useState<string>('all');
  const [selectedWing, setSelectedWing] = useState<string>('all');
  const [selectedFloor, setSelectedFloor] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Feed items & query state
  const [feedItems, setFeedItems] = useState<(FeedItem | HostelFeedItem)[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [hostelFeedNotice, setHostelFeedNotice] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState<number>(0);

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

  // Load feed items whenever department or status selection changes, or on retry
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setHostelFeedNotice(null);

    const statusParam = selectedStatus !== 'all' ? selectedStatus : undefined;

    async function fetchFeed() {
      try {
        let combined: (FeedItem | HostelFeedItem)[] = [];

        // Scenario 1: Specific non-Hostel department
        if (selectedDeptId !== 'all') {
          const dept = departments.find((d) => String(d.id) === selectedDeptId);
          if (dept && isHostelDepartment(dept)) {
            // Hostel department selected -> use hostel feed
            try {
              const res = await getHostelFeedApi({
                status: statusParam,
                limit: 100,
                signal: controller.signal,
              });
              combined = res.items;
            } catch (err: unknown) {
              const errDetail = (err as { rawDetail?: { code?: string; message?: string } })?.rawDetail;
              if (errDetail?.code === 'residence_not_verified') {
                setHostelFeedNotice('Hostel complaints require a verified student residence.');
              } else {
                throw err;
              }
            }
          } else {
            // Non-hostel department -> use department feed
            const res = await getDepartmentFeedApi(Number(selectedDeptId), {
              status: statusParam,
              limit: 100,
              signal: controller.signal,
            });
            combined = res.items;
          }
        } else {
          // Scenario 2: All Departments
          const activeDepts = departments.filter((d) => d.is_active !== false);
          const nonHostelDepts = activeDepts.filter((d) => !isHostelDepartment(d));
          const hasHostelDept = activeDepts.some((d) => isHostelDepartment(d));

          // Fetch from non-hostel departments in parallel
          const deptPromises = nonHostelDepts.map(async (d) => {
            try {
              const res = await getDepartmentFeedApi(d.id, {
                status: statusParam,
                limit: 50,
                signal: controller.signal,
              });
              return { ok: true as const, items: res.items };
            } catch (err) {
              return { ok: false as const, error: err };
            }
          });

          // Attempt to fetch hostel feed if available
          let hostelItems: HostelFeedItem[] = [];
          if (hasHostelDept || departments.length === 0) {
            try {
              const hostelRes = await getHostelFeedApi({
                status: statusParam,
                limit: 50,
                signal: controller.signal,
              });
              hostelItems = hostelRes.items;
            } catch (err: unknown) {
              const errDetail = (err as { rawDetail?: { code?: string; message?: string }; status?: number })?.rawDetail;
              if (errDetail?.code === 'residence_not_verified' || (err as { status?: number }).status === 403) {
                // Gracefully ignore unverified residence or role restriction in aggregate view
              } else {
                throw err;
              }
            }
          }

          const deptResults = await Promise.all(deptPromises);
          const firstFailure = deptResults.find((r) => !r.ok);
          if (firstFailure && !firstFailure.ok) {
            throw firstFailure.error;
          }
          const allDeptItems = deptResults.flatMap((r) => (r.ok ? r.items : []));

          // Deduplicate by complaint ID
          const seenIds = new Set<number>();
          combined = [...hostelItems, ...allDeptItems].filter((item) => {
            if (seenIds.has(item.id)) return false;
            seenIds.add(item.id);
            return true;
          });

          // Sort descending by created_at, then id
          combined.sort((a, b) => {
            const timeA = new Date(a.created_at).getTime();
            const timeB = new Date(b.created_at).getTime();
            if (timeA !== timeB) return timeB - timeA;
            return b.id - a.id;
          });
        }

        if (!controller.signal.aborted) {
          setFeedItems(combined);
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(errorMessage(err, 'Failed to load public complaints feed.'));
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    if (!metaLoading) {
      fetchFeed();
    }

    return () => controller.abort();
  }, [selectedDeptId, selectedStatus, reloadKey, departments, metaLoading, isHostelDepartment]);

  // Derived options for location hierarchy
  const availableHostels = useMemo(() => locations.map((h) => h.name), [locations]);

  const selectedHostelNode = useMemo(
    () => locations.find((h) => h.name === selectedHostel),
    [locations, selectedHostel],
  );

  const availableWings = useMemo(() => {
    if (!selectedHostelNode) return [];
    return selectedHostelNode.wings.map((w) => w.name);
  }, [selectedHostelNode]);

  const selectedWingNode = useMemo(() => {
    if (!selectedHostelNode) return null;
    return selectedHostelNode.wings.find((w) => w.name === selectedWing);
  }, [selectedHostelNode, selectedWing]);

  const availableFloors = useMemo(() => {
    if (!selectedWingNode) return [];
    return selectedWingNode.floors.map((f) => f.name);
  }, [selectedWingNode]);

  // Handle hostel filter change: reset wing and floor
  const handleHostelChange = (hostelName: string) => {
    setSelectedHostel(hostelName);
    setSelectedWing('all');
    setSelectedFloor('all');
  };

  // Handle wing filter change: reset floor
  const handleWingChange = (wingName: string) => {
    setSelectedWing(wingName);
    setSelectedFloor('all');
  };

  // Reset all filters
  const resetFilters = () => {
    setSelectedDeptId('all');
    setSelectedStatus('all');
    setSelectedHostel('all');
    setSelectedWing('all');
    setSelectedFloor('all');
    setSearchQuery('');
  };

  const isFilterActive =
    selectedDeptId !== 'all' ||
    selectedStatus !== 'all' ||
    selectedHostel !== 'all' ||
    selectedWing !== 'all' ||
    selectedFloor !== 'all' ||
    Boolean(searchQuery.trim());

  // Filter items client-side for location and search query
  const filteredItems = useMemo(() => {
    return feedItems.filter((item) => {
      // Hostel filter
      if (selectedHostel !== 'all') {
        if (!item.hostel || item.hostel.toLowerCase() !== selectedHostel.toLowerCase()) {
          return false;
        }
      }
      // Wing filter
      if (selectedWing !== 'all') {
        if (!item.wing || item.wing.toLowerCase() !== selectedWing.toLowerCase()) {
          return false;
        }
      }
      // Floor filter
      if (selectedFloor !== 'all') {
        if (!item.floor || item.floor.toLowerCase() !== selectedFloor.toLowerCase()) {
          return false;
        }
      }
      // Search query (title or reference number)
      if (searchQuery.trim()) {
        const query = searchQuery.trim().toLowerCase();
        const matchesTitle = item.title.toLowerCase().includes(query);
        const matchesRef = String(item.id).includes(query);
        if (!matchesTitle && !matchesRef) return false;
      }
      return true;
    });
  }, [feedItems, selectedHostel, selectedWing, selectedFloor, searchQuery]);

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
              onChange={(e) => setSelectedDeptId(e.target.value)}
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
              onChange={(e) => setSelectedStatus(e.target.value)}
              disabled={loading && metaLoading}
            >
              <option value="all">All Statuses</option>
              <option value="submitted">Submitted</option>
              <option value="in_progress">In Progress</option>
              <option value="resolved">Resolved</option>
              <option value="reopened">Reopened</option>
            </select>
          </div>

          {/* Hostel Filter */}
          <div className="feed-filter-group">
            <label htmlFor="feed-hostel-filter">Hostel</label>
            <select
              id="feed-hostel-filter"
              value={selectedHostel}
              onChange={(e) => handleHostelChange(e.target.value)}
              disabled={loading && metaLoading}
            >
              <option value="all">All Hostels</option>
              {availableHostels.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>

          {/* Wing Filter */}
          <div className="feed-filter-group">
            <label htmlFor="feed-wing-filter">Wing</label>
            <select
              id="feed-wing-filter"
              value={selectedWing}
              onChange={(e) => handleWingChange(e.target.value)}
              disabled={selectedHostel === 'all' || availableWings.length === 0}
            >
              <option value="all">All Wings</option>
              {availableWings.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>

          {/* Floor Filter */}
          <div className="feed-filter-group">
            <label htmlFor="feed-floor-filter">Floor</label>
            <select
              id="feed-floor-filter"
              value={selectedFloor}
              onChange={(e) => setSelectedFloor(e.target.value)}
              disabled={selectedWing === 'all' || availableFloors.length === 0}
            >
              <option value="all">All Floors</option>
              {availableFloors.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>

          {/* Search Query */}
          <div className="feed-filter-group">
            <label htmlFor="feed-search-filter">Search title or #ID</label>
            <input
              id="feed-search-filter"
              type="text"
              placeholder="e.g. WiFi or 42"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        {/* Toolbar Actions & Summary */}
        <div className="feed-toolbar__actions">
          <span className="feed-count-summary">
            {loading ? (
              'Loading complaints...'
            ) : (
              `Showing ${filteredItems.length} public complaint${filteredItems.length === 1 ? '' : 's'}`
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
      ) : filteredItems.length === 0 ? (
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
      ) : (
        <div className="feed-list" role="feed" aria-label="Campus public complaints">
          {filteredItems.map((item) => {
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
    </div>
  );
}
