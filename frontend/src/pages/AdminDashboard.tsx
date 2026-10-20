import { ReactNode, useCallback, useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { getHealthApi, getReadinessApi } from '../api/system';
import { getDepartmentsApi } from '../api/departments';
import { errorMessage } from '../api/client';
import { Department, HealthResponse, ReadinessResponse } from '../types';
import { Alert, Button, DetailList, PageHeader, Panel, Skeleton } from '../components/ui';
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
  useDocumentTitle('System overview');
  const { user } = useAuth();
  const [health, setHealth] = useState<Load<HealthResponse>>({ state: 'loading' });
  const [ready, setReady] = useState<Load<ReadinessResponse>>({ state: 'loading' });
  const [departments, setDepartments] = useState<Load<Department[]>>({ state: 'loading' });

  const load = useCallback((signal?: AbortSignal) => {
    setHealth({ state: 'loading' });
    setReady({ state: 'loading' });
    setDepartments({ state: 'loading' });
    const settle = <T,>(p: Promise<T>, set: (v: Load<T>) => void) =>
      p
        .then((data) => set({ state: 'ok', data, checkedAt: new Date() }))
        .catch((err) => {
          if (!signal?.aborted) set({ state: 'error', message: errorMessage(err) });
        });
    settle(getHealthApi(signal), setHealth);
    settle(getReadinessApi(signal), setReady);
    settle(getDepartmentsApi(signal), setDepartments);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  // Every indicator reflects an actual response. A failed request is shown as
  // "Unreachable" — never as operational.
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

  return (
    <div>
      <PageHeader
        title="System overview"
        description="Live status of the CCMS backend and the department catalogue students can route complaints to."
        actions={
          <Button variant="secondary" icon="refresh" onClick={() => load()}>
            Check again
          </Button>
        }
      />

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
                value: checkedAt ? checkedAt.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', second: '2-digit' }) : '—',
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

      <Panel
        title={
          departments.state === 'ok' ? `Active departments (${departments.data.length})` : 'Active departments'
        }
        className="mt-6"
      >
        {departments.state === 'loading' ? (
          <div className="row-skeletons">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} height={18} width={`${60 + ((i * 13) % 30)}%`} />
            ))}
          </div>
        ) : departments.state === 'error' ? (
          <Alert tone="error">Departments couldn't be loaded: {departments.message}</Alert>
        ) : departments.data.length === 0 ? (
          <p className="muted-note">No active departments. Run the department seed script on the server.</p>
        ) : (
          <table className="dept-table">
            <thead>
              <tr>
                <th scope="col">Department</th>
                <th scope="col">Scope</th>
              </tr>
            </thead>
            <tbody>
              {departments.data.map((d) => (
                <tr key={d.id}>
                  <th scope="row">{d.name}</th>
                  <td>{d.description || 'No description'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
