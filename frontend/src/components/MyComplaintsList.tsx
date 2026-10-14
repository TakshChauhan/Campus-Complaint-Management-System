import React, { useState, useEffect } from 'react';
import { ComplaintListItem } from '../types';
import { getMyComplaintsApi } from '../api/complaints';
import './MyComplaintsList.css';

interface Props {
  onRegisterNew: () => void;
}

export default function MyComplaintsList({ onRegisterNew }: Props) {
  const [complaints, setComplaints] = useState<ComplaintListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchComplaints = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getMyComplaintsApi();
      setComplaints(data);
    } catch (err: any) {
      setError(err.message || 'Failed to retrieve complaint history.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchComplaints();
  }, []);

  return (
    <div className="my-complaints-wrapper">
      <div className="history-header">
        <div className="history-title-group">
          <h2>
            My Registered Complaints
            {!isLoading && !error && (
              <span className="history-count-badge">
                {complaints.length} {complaints.length === 1 ? 'record' : 'records'}
              </span>
            )}
          </h2>
        </div>

        <div className="history-header-actions">
          <button
            type="button"
            className="btn-secondary"
            onClick={fetchComplaints}
            disabled={isLoading}
            title="Refresh list from server"
          >
            {isLoading ? 'Refreshing...' : '↻ Refresh'}
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={onRegisterNew}
          >
            + Register Complaint
          </button>
        </div>
      </div>

      {error && (
        <div className="form-error-banner" role="alert">
          {error}{' '}
          <button
            type="button"
            onClick={fetchComplaints}
            style={{ textDecoration: 'underline', background: 'none', border: 'none', cursor: 'pointer' }}
          >
            Retry
          </button>
        </div>
      )}

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: '48px', color: 'var(--color-text-muted)' }}>
          Retrieving your registered complaints from database...
        </div>
      ) : complaints.length === 0 ? (
        <div className="empty-state-box">
          <div className="empty-state-icon" aria-hidden="true">📋</div>
          <h3>No Complaints Registered Yet</h3>
          <p>
            You have not submitted any complaints. If you encounter any infrastructure, hostel, Wi-Fi, or facility issue on campus, register it here.
          </p>
          <button
            type="button"
            className="btn-primary"
            onClick={onRegisterNew}
            style={{ marginTop: 'var(--space-sm)' }}
          >
            Register Your First Complaint
          </button>
        </div>
      ) : (
        <div className="complaints-list">
          {complaints.map((item) => {
            const formattedDate = item.created_at
              ? new Date(item.created_at).toLocaleString('en-GB', {
                  day: '2-digit',
                  month: 'short',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })
              : 'Unknown date';

            return (
              <article key={item.id} className="complaint-item-card">
                <div className="complaint-card-meta">
                  <div className="meta-left">
                    <span className="complaint-id-tag">CMP-{item.id}</span>
                    <span className="complaint-dept-badge">{item.department_name}</span>
                  </div>
                  <span className="status-pill-submitted">
                    <span className="status-dot"></span>
                    {item.status === 'submitted' ? 'Submitted' : item.status}
                  </span>
                </div>

                <h3 className="complaint-card-title">{item.title}</h3>

                <div className="complaint-card-footer">
                  <span>Registered: {formattedDate}</span>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
