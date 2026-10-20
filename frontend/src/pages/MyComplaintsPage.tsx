import { useCallback, useEffect, useRef, useState } from 'react';
import { getMyComplaintsApi } from '../api/complaints';
import { getDepartmentsApi } from '../api/departments';
import { errorMessage } from '../api/client';
import { ComplaintPage, Department } from '../types';
import { Alert, Button, ButtonLink, EmptyState, Icon, PageHeader, Panel, Skeleton } from '../components/ui';
import { ComplaintRow } from '../components/ComplaintRow';
import { useSearchParams } from '../lib/router';
import { useDebouncedValue, useDocumentTitle } from '../hooks/useMediaState';

export const PAGE_SIZE = 10;

export default function MyComplaintsPage() {
  useDocumentTitle('My complaints');
  // Filters live in the URL so refresh/back keep the same view.
  const [params, setParams] = useSearchParams();
  const pageNumber = Math.max(1, Number.parseInt(params.get('page') ?? '1', 10) || 1);
  const sort = params.get('sort') === 'oldest' ? 'oldest' : 'newest';
  const departmentId = params.get('department') ?? '';
  const urlQuery = params.get('q') ?? '';

  const [searchInput, setSearchInput] = useState(urlQuery);
  const debouncedSearch = useDebouncedValue(searchInput.trim(), 350);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [result, setResult] = useState<ComplaintPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  // Push the debounced search term into the URL and return to page 1. Only a
  // change of the debounced value triggers this (not URL changes such as
  // "Clear filters"), so a stale term is never written back.
  const urlQueryRef = useRef(urlQuery);
  urlQueryRef.current = urlQuery;
  const setParamsRef = useRef(setParams);
  setParamsRef.current = setParams;
  useEffect(() => {
    if (debouncedSearch !== urlQueryRef.current) setParamsRef.current({ q: debouncedSearch || null, page: null });
  }, [debouncedSearch]);

  useEffect(() => {
    const controller = new AbortController();
    getDepartmentsApi(controller.signal)
      .then(setDepartments)
      .catch(() => {
        /* The filter simply stays empty; the list still works. */
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getMyComplaintsApi(
      {
        limit: PAGE_SIZE,
        offset: (pageNumber - 1) * PAGE_SIZE,
        q: urlQuery || undefined,
        department_id: departmentId ? Number(departmentId) : undefined,
        sort,
      },
      controller.signal,
    )
      .then((data) => setResult(data))
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(errorMessage(err, "Couldn't load your complaints."));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [pageNumber, sort, departmentId, urlQuery, reloadKey]);

  const retry = useCallback(() => setReloadKey((k) => k + 1), []);

  const total = result?.total ?? null;
  const items = result?.items ?? [];
  const filtersActive = Boolean(urlQuery || departmentId);
  const firstIndex = (pageNumber - 1) * PAGE_SIZE + 1;
  const lastIndex = firstIndex + items.length - 1;
  const totalPages = total !== null ? Math.max(1, Math.ceil(total / PAGE_SIZE)) : null;
  // Without a total, a full page means there may be more.
  const hasNext = totalPages !== null ? pageNumber < totalPages : items.length === PAGE_SIZE;

  // If a filter change leaves us beyond the last page, go back to the last page.
  useEffect(() => {
    if (!loading && totalPages !== null && pageNumber > totalPages) setParams({ page: String(totalPages) });
  }, [loading, totalPages, pageNumber, setParams]);

  const clearFilters = () => {
    setSearchInput('');
    setParams({ q: null, department: null, page: null });
  };

  return (
    <div>
      <PageHeader
        title="My complaints"
        description="Everything you have submitted, newest first. Search covers your full history."
        actions={
          <ButtonLink to="/complaints/new" icon="plus">
            Raise complaint
          </ButtonLink>
        }
      />

      <Panel>
        <div className="list-toolbar" role="search">
          <label className="search-input">
            <span className="visually-hidden">Search your complaints</span>
            <Icon name="search" size={18} />
            <input
              type="search"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search reference, title or description"
              maxLength={120}
            />
          </label>
          <label className="toolbar-select">
            <span className="toolbar-select__label">Department</span>
            <select value={departmentId} onChange={(e) => setParams({ department: e.target.value || null, page: null })}>
              <option value="">All departments</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
          <label className="toolbar-select">
            <span className="toolbar-select__label">Sort</span>
            <select value={sort} onChange={(e) => setParams({ sort: e.target.value === 'oldest' ? 'oldest' : null, page: null })}>
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
            </select>
          </label>
        </div>

        <div className="list-summary" aria-live="polite">
          {!loading && !error && total !== null ? (
            total === 0 ? null : (
              <span>
                Showing {firstIndex}–{lastIndex} of {total} {filtersActive ? 'matching ' : ''}
                {total === 1 ? 'complaint' : 'complaints'}
              </span>
            )
          ) : null}
          {filtersActive ? (
            <Button variant="ghost" size="sm" onClick={clearFilters}>
              Clear search and filters
            </Button>
          ) : null}
        </div>

        {error ? (
          <Alert
            tone="error"
            title="Couldn't load your complaints"
            action={
              <Button size="sm" variant="secondary" icon="refresh" onClick={retry}>
                Retry
              </Button>
            }
          >
            {error}
          </Alert>
        ) : loading && !result ? (
          <div className="row-skeletons" aria-busy="true" aria-label="Loading complaints">
            {Array.from({ length: 4 }).map((_, i) => (
              <div className="row-skeleton" key={i}>
                <Skeleton width="28%" height={12} />
                <Skeleton width="65%" height={16} />
                <Skeleton width="90%" height={12} />
              </div>
            ))}
          </div>
        ) : items.length === 0 ? (
          filtersActive ? (
            <EmptyState icon="search" title="No complaints match" action={<Button variant="secondary" onClick={clearFilters}>Clear search and filters</Button>}>
              Try a different reference or keyword, or choose another department.
            </EmptyState>
          ) : (
            <EmptyState title="No complaints yet" action={<ButtonLink to="/complaints/new" icon="plus">Raise your first complaint</ButtonLink>}>
              Complaints you submit appear here with their reference, department and status.
            </EmptyState>
          )
        ) : (
          <ul className={['complaint-rows', loading && 'is-refreshing'].filter(Boolean).join(' ')} aria-busy={loading || undefined}>
            {items.map((item) => (
              <li key={item.id}>
                <ComplaintRow item={item} />
              </li>
            ))}
          </ul>
        )}

        {!error && (pageNumber > 1 || hasNext) ? (
          <nav className="pagination" aria-label="Complaint pages">
            <Button
              variant="secondary"
              size="sm"
              icon="chevronLeft"
              disabled={pageNumber <= 1 || loading}
              onClick={() => setParams({ page: pageNumber - 1 > 1 ? String(pageNumber - 1) : null })}
            >
              Previous
            </Button>
            <span className="pagination__status">
              Page {pageNumber}
              {totalPages !== null ? ` of ${totalPages}` : ''}
            </span>
            <Button
              variant="secondary"
              size="sm"
              iconAfter="chevronRight"
              disabled={!hasNext || loading}
              onClick={() => setParams({ page: String(pageNumber + 1) })}
            >
              Next
            </Button>
          </nav>
        ) : null}
      </Panel>
    </div>
  );
}
