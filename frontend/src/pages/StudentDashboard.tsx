import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { getMyComplaintsApi } from '../api/complaints';
import { errorMessage } from '../api/client';
import { ComplaintPage } from '../types';
import { Alert, Button, ButtonLink, EmptyState, Panel, Skeleton } from '../components/ui';
import { ComplaintRow } from '../components/ComplaintRow';
import { CAMPUS_AERIAL } from '../lib/campusPhotos';
import { firstName } from '../lib/format';
import { useDocumentTitle } from '../hooks/useMediaState';

const RECENT_LIMIT = 5;

export default function StudentDashboard() {
  useDocumentTitle('Dashboard');
  const { user } = useAuth();
  const [page, setPage] = useState<ComplaintPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    getMyComplaintsApi({ limit: RECENT_LIMIT, offset: 0 }, signal)
      .then((result) => setPage(result))
      .catch((err) => {
        if (signal?.aborted) return;
        setError(errorMessage(err, "Couldn't load your complaints."));
      })
      .finally(() => {
        if (!signal?.aborted) setLoading(false);
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const name = firstName(user?.name);

  return (
    <div className="dashboard">
      <section className="hero" aria-labelledby="welcome-heading">
        <img
          className="hero__img"
          src={CAMPUS_AERIAL.src}
          srcSet={CAMPUS_AERIAL.srcSet}
          sizes="(max-width: 960px) 100vw, 1080px"
          alt="Aerial view of the DAU academic blocks surrounded by trees"
          style={{ objectPosition: '50% 58%' }}
        />
        <div className="hero__scrim" aria-hidden="true" />
        <div className="hero__content">
          <h1 id="welcome-heading" className="hero__title">
            Welcome back{name ? `, ${name}` : ''}
          </h1>
          <p className="hero__text">Manage and track your campus complaints in one place.</p>
          <div className="hero__actions">
            <ButtonLink to="/complaints/new" icon="plus">
              Raise new complaint
            </ButtonLink>
            <ButtonLink to="/complaints" variant="secondary" icon="list">
              View my complaints
            </ButtonLink>
          </div>
        </div>
      </section>

      <div className="dashboard__grid">
        <Panel className="stat-panel" as="div">
          <p className="stat-panel__label" id="total-label">
            Complaints you have submitted
          </p>
          {loading && !page ? (
            <Skeleton width={64} height={40} />
          ) : page && page.total !== null ? (
            <p className="stat-panel__value" aria-labelledby="total-label">
              {page.total}
            </p>
          ) : (
            <p className="stat-panel__unavailable">{error ? 'Unavailable right now' : 'Not available'}</p>
          )}
          <p className="stat-panel__note">Every complaint stays in your history with the reference shown when you submitted it.</p>
        </Panel>

        <Panel
          title="Recent complaints"
          className="recent-panel"
          action={
            page && page.items.length > 0 ? (
              <ButtonLink to="/complaints" variant="ghost" size="sm">
                See all
              </ButtonLink>
            ) : null
          }
        >
          {error ? (
            <Alert
              tone="error"
              title="Couldn't load your complaints"
              action={
                <Button size="sm" variant="secondary" icon="refresh" onClick={() => load()}>
                  Retry
                </Button>
              }
            >
              {error}
            </Alert>
          ) : loading && !page ? (
            <div className="row-skeletons" aria-busy="true" aria-label="Loading recent complaints">
              {Array.from({ length: 3 }).map((_, i) => (
                <div className="row-skeleton" key={i}>
                  <Skeleton width="30%" height={12} />
                  <Skeleton width="70%" height={16} />
                </div>
              ))}
            </div>
          ) : page && page.items.length === 0 ? (
            <EmptyState
              title="You haven't raised a complaint yet"
              action={<ButtonLink to="/complaints/new" icon="plus">Raise a complaint</ButtonLink>}
            >
              When something on campus needs fixing — a hostel tap, Wi-Fi in a lab, a library terminal — raise it here and
              keep the reference for follow-up.
            </EmptyState>
          ) : (
            <ul className="complaint-rows">
              {page?.items.map((item) => (
                <li key={item.id}>
                  <ComplaintRow item={item} compact />
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
