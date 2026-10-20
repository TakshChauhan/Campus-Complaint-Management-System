import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { getDepartmentsApi } from '../api/departments';
import { errorMessage } from '../api/client';
import { Department } from '../types';
import { Alert, Button, DetailList, Icon, PageHeader, Panel, Skeleton } from '../components/ui';
import { firstName } from '../lib/format';
import { useDocumentTitle } from '../hooks/useMediaState';

export default function StaffDashboard() {
  useDocumentTitle('Staff overview');
  const { user } = useAuth();
  const [department, setDepartment] = useState<Department | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    (signal?: AbortSignal) => {
      setState('loading');
      getDepartmentsApi(signal)
        .then((list) => {
          setDepartment(user?.department_id ? list.find((d) => d.id === user.department_id) ?? null : null);
          setState('ready');
        })
        .catch((err) => {
          if (signal?.aborted) return;
          setError(errorMessage(err));
          setState('error');
        });
    },
    [user?.department_id],
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  if (!user) return null;

  const departmentValue =
    state === 'loading' ? (
      <Skeleton width={140} height={16} />
    ) : department ? (
      department.name
    ) : user.department_id ? (
      `Department #${user.department_id} (not in the active catalogue)`
    ) : (
      'No department assigned'
    );

  return (
    <div>
      <PageHeader
        title={`Hello, ${firstName(user.name) || 'colleague'}`}
        description="Your staff account on the DAU Campus Complaint Management System."
      />

      <div className="staff-grid">
        <Panel title="Your account">
          <DetailList
            items={[
              { label: 'Name', value: user.name },
              { label: 'Email', value: user.email },
              { label: 'Department', value: departmentValue },
            ]}
          />
          {state === 'error' ? (
            <Alert
              tone="error"
              className="mt-4"
              action={
                <Button size="sm" variant="secondary" icon="refresh" onClick={() => load()}>
                  Retry
                </Button>
              }
            >
              Department details couldn't be loaded. {error}
            </Alert>
          ) : null}
          {department?.description ? <p className="muted-note">{department.description}</p> : null}
        </Panel>

        <Panel title="What's available in this release">
          <ul className="scope-list">
            <li>
              <Icon name="check" size={18} />
              <span>Sign in and view your staff profile and assigned department.</span>
            </li>
            <li>
              <Icon name="check" size={18} />
              <span>Students raise complaints and route them to departments, including yours.</span>
            </li>
            <li className="is-later">
              <Icon name="info" size={18} />
              <span>
                A department complaint queue, status updates and resolution remarks are planned for the next sprint. They are
                not shown here because they don't exist yet.
              </span>
            </li>
          </ul>
        </Panel>
      </div>
    </div>
  );
}
