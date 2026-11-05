import { useCallback, useEffect, useState } from 'react';
import { getCoverageGapsApi } from '../api/admin';
import { errorMessage } from '../api/client';
import { CoverageGapItem } from '../types';
import { Alert, Panel, Skeleton } from './ui';

type Load<T> =
  | { state: 'loading' }
  | { state: 'ok'; data: T }
  | { state: 'error'; message: string };

export function CoverageGapsSection() {
  const [gaps, setGaps] = useState<Load<CoverageGapItem[]>>({ state: 'loading' });

  const load = useCallback((signal?: AbortSignal) => {
    setGaps({ state: 'loading' });
    getCoverageGapsApi(signal)
      .then((data) => setGaps({ state: 'ok', data }))
      .catch((err) => {
        if (!signal?.aborted) setGaps({ state: 'error', message: errorMessage(err) });
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  return (
    <Panel
      title={
        gaps.state === 'ok'
          ? `Hostel coverage gaps (${gaps.data.length})`
          : 'Hostel coverage gaps'
      }
      className="mt-6"
    >
      {gaps.state === 'loading' ? (
        <div className="row-skeletons" aria-label="Loading coverage gaps">
          <Skeleton height={24} width="80%" />
          <Skeleton height={24} width="60%" />
        </div>
      ) : gaps.state === 'error' ? (
        <Alert tone="error">Coverage gaps could not be loaded: {gaps.message}</Alert>
      ) : gaps.data.length === 0 ? (
        <p className="muted-note">No coverage gaps. All hostels with open complaints have assigned staff.</p>
      ) : (
        <table className="dept-table" aria-label="Hostels with open complaints and no assigned staff">
          <thead>
            <tr>
              <th scope="col">Hostel</th>
              <th scope="col" style={{ textAlign: 'right' }}>Open complaints</th>
            </tr>
          </thead>
          <tbody>
            {gaps.data.map((item) => (
              <tr key={item.hostel_id}>
                <th scope="row">{item.hostel_name}</th>
                <td style={{ textAlign: 'right' }}>
                  <span className="badge badge--warning">{item.open_count}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
