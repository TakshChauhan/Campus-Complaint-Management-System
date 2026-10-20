import { useEffect, useState } from 'react';
import { getMyComplaintApi } from '../api/complaints';
import { ApiClientError, errorMessage } from '../api/client';
import { ComplaintResponse } from '../types';
import { Alert, Button, ButtonLink, CopyButton, DetailList, EmptyState, Icon, Panel, Skeleton, StatusBadge } from '../components/ui';
import { Link } from '../lib/router';
import { complaintReference, formatDateTime } from '../lib/format';
import { useDocumentTitle } from '../hooks/useMediaState';

export default function ComplaintDetailPage({ id }: { id: number }) {
  const reference = complaintReference(id);
  useDocumentTitle(reference);
  const [complaint, setComplaint] = useState<ComplaintResponse | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'not_found' | 'error'>('loading');
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState('loading');
    getMyComplaintApi(id, controller.signal)
      .then((data) => {
        setComplaint(data);
        setState('ready');
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        if (err instanceof ApiClientError && err.status === 404) setState('not_found');
        else {
          setError(errorMessage(err));
          setState('error');
        }
      });
    return () => controller.abort();
  }, [id, reloadKey]);

  return (
    <div className="detail-page">
      <Link to="/complaints" className="back-link">
        <Icon name="arrowLeft" size={18} /> My complaints
      </Link>

      {state === 'loading' ? (
        <Panel>
          <div className="row-skeleton" aria-busy="true" aria-label="Loading complaint">
            <Skeleton width="20%" height={14} />
            <Skeleton width="60%" height={26} />
            <Skeleton width="100%" height={80} />
          </div>
        </Panel>
      ) : state === 'not_found' ? (
        <Panel>
          <EmptyState icon="search" title={`${reference} not found`} action={<ButtonLink to="/complaints">Back to my complaints</ButtonLink>}>
            There's no complaint with this reference in your history.
          </EmptyState>
        </Panel>
      ) : state === 'error' ? (
        <Alert
          tone="error"
          title="Couldn't load this complaint"
          action={
            <Button size="sm" variant="secondary" icon="refresh" onClick={() => setReloadKey((k) => k + 1)}>
              Retry
            </Button>
          }
        >
          {error}
        </Alert>
      ) : complaint ? (
        <Panel as="article">
          <header className="detail-head">
            <div className="detail-head__ref">
              <span>{reference}</span>
              <CopyButton value={reference} label="Copy reference" />
            </div>
            <h1 className="detail-head__title">{complaint.title}</h1>
            <StatusBadge status={complaint.status} />
          </header>

          <section className="detail-section" aria-labelledby="desc-heading">
            <h2 id="desc-heading" className="detail-section__title">
              Description
            </h2>
            <p className="detail-description">{complaint.description}</p>
          </section>

          <section className="detail-section" aria-labelledby="info-heading">
            <h2 id="info-heading" className="detail-section__title">
              Details
            </h2>
            <DetailList
              items={[
                { label: 'Department', value: complaint.department_name },
                { label: 'Submitted', value: formatDateTime(complaint.created_at) },
                { label: 'Current status', value: <StatusBadge status={complaint.status} /> },
              ]}
            />
          </section>

          <p className="detail-note">
            <Icon name="info" size={16} />
            Department review, status changes and replies are planned for a later release. Until then, the status shown here
            is the one stored for this complaint.
          </p>
        </Panel>
      ) : null}
    </div>
  );
}
