import React, { useState } from 'react';
import { ComplaintResponse } from '../types';
import './ComplaintReceipt.css';

interface Props {
  complaint: ComplaintResponse;
  onViewMyComplaints: () => void;
  onRegisterAnother: () => void;
}

export default function ComplaintReceipt({
  complaint,
  onViewMyComplaints,
  onRegisterAnother,
}: Props) {
  // Option 4B: Description preview toggle (start collapsed)
  const [isExpanded, setIsExpanded] = useState(false);

  const formattedDate = complaint.created_at
    ? new Date(complaint.created_at).toLocaleString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : 'Just now';

  return (
    <div className="receipt-wrapper">
      {/* Header with success indicator */}
      <div className="receipt-header">
        <div className="receipt-success-icon" aria-hidden="true">✓</div>
        <div className="receipt-header-text">
          <h2>Complaint Successfully Registered</h2>
          <p>Your complaint has been committed to the database and assigned to the relevant department.</p>
        </div>
      </div>

      {/* Summary Box (Option 1B: Compact borderless card) */}
      <div className="receipt-summary-box">
        <div className="receipt-row">
          <span className="receipt-label">Reference ID</span>
          <span className="receipt-value">
            <span className="receipt-id-badge">CMP-{complaint.id}</span>
          </span>
        </div>

        <div className="receipt-row">
          <span className="receipt-label">Status</span>
          <span className="receipt-value">
            {/* Option 2A: Descriptive Pill Badge */}
            <span className="status-pill-submitted">
              <span className="status-dot"></span>
              {complaint.status === 'submitted' ? 'Submitted (Pending Review)' : complaint.status}
            </span>
          </span>
        </div>

        <div className="receipt-row">
          <span className="receipt-label">Assigned Department</span>
          <span className="receipt-value">{complaint.department_name}</span>
        </div>

        <div className="receipt-row">
          <span className="receipt-label">Complaint Title</span>
          <span className="receipt-value">{complaint.title}</span>
        </div>

        <div className="receipt-row">
          <span className="receipt-label">Filed On</span>
          <span className="receipt-value">{formattedDate}</span>
        </div>

        {/* Option 4B: Description with Expand/Collapse toggle */}
        <div className="receipt-row" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
          <span className="receipt-label">Submitted Description</span>
          <div className="receipt-description-box">
            <p className={`receipt-description-text ${!isExpanded ? 'clamped' : ''}`}>
              {complaint.description}
            </p>
            <button
              type="button"
              className="btn-toggle-description"
              onClick={() => setIsExpanded(!isExpanded)}
            >
              {isExpanded ? 'Show less' : 'Show full description'}
            </button>
          </div>
        </div>
      </div>

      {/* Actions (Option 3A: Dual Action Buttons with uniform button colors) */}
      <div className="receipt-actions">
        <button
          type="button"
          className="btn-secondary"
          onClick={onRegisterAnother}
        >
          Register Another Complaint
        </button>
        <button
          type="button"
          className="btn-primary"
          onClick={onViewMyComplaints}
        >
          Go to My Complaints
        </button>
      </div>
    </div>
  );
}
