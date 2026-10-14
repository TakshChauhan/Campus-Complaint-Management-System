import React, { useState, useEffect } from 'react';
import { Department, DepartmentSuggestionItem, ComplaintResponse } from '../types';
import { getDepartmentsApi, suggestDepartmentApi } from '../api/departments';
import { createComplaintApi } from '../api/complaints';
import { ApiClientError } from '../api/client';
import './SubmitComplaintForm.css';

interface Props {
  onSubmitSuccess: (newComplaint: ComplaintResponse) => void;
}

export default function SubmitComplaintForm({ onSubmitSuccess }: Props) {
  // Real departments loaded from backend
  const [departments, setDepartments] = useState<Department[]>([]);
  const [isLoadingDepts, setIsLoadingDepts] = useState(true);
  const [deptLoadError, setDeptLoadError] = useState<string | null>(null);

  // Form field states
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [selectedDepartmentId, setSelectedDepartmentId] = useState<number | ''>('');

  // Department suggestion states
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [suggestion, setSuggestion] = useState<DepartmentSuggestionItem | null>(null);
  const [suggestionNotice, setSuggestionNotice] = useState<string | null>(null);
  const [showSuggestion, setShowSuggestion] = useState<boolean>(true);

  // Submission states
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Load real departments from backend on mount
  useEffect(() => {
    loadDepartments();
  }, []);

  const loadDepartments = async () => {
    setIsLoadingDepts(true);
    setDeptLoadError(null);
    try {
      const data = await getDepartmentsApi();
      setDepartments(data);
    } catch (err: any) {
      setDeptLoadError(err.message || 'Failed to load campus departments.');
    } finally {
      setIsLoadingDepts(false);
    }
  };

  // Request advisory keyword-based recommendation from backend POST /api/v1/departments/suggest
  const handleRequestSuggestion = async () => {
    const trimmedTitle = title.trim();
    const trimmedDesc = description.trim();

    if (trimmedTitle.length < 3 || trimmedDesc.length < 10) {
      setSuggestionNotice('Enter at least 3 characters for title and 10 characters for description to request a recommendation.');
      return;
    }

    setIsSuggesting(true);
    setSuggestionNotice(null);
    try {
      const res = await suggestDepartmentApi(trimmedTitle, trimmedDesc);
      if (res.suggestions && res.suggestions.length > 0) {
        setSuggestion(res.suggestions[0]);
        setShowSuggestion(true);
      } else {
        setSuggestion(null);
        setSuggestionNotice('No specific department confidently matched your issue keywords. Please choose manually from the dropdown.');
      }
    } catch (err: any) {
      setSuggestion(null);
      setSuggestionNotice('Advisory suggestion service is temporarily unavailable. Please select your department manually.');
    } finally {
      setIsSuggesting(false);
    }
  };

  // Apply suggestion to the dropdown
  const handleAcceptSuggestion = () => {
    if (suggestion) {
      setSelectedDepartmentId(suggestion.department_id);
    }
  };

  // Handle real form submission to backend POST /api/v1/complaints
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);

    const trimmedTitle = title.trim();
    const trimmedDesc = description.trim();

    // Client-side validations matching backend constraints
    if (trimmedTitle.length < 3) {
      setSubmitError('Title must be at least 3 characters long.');
      return;
    }
    if (trimmedTitle.length > 120) {
      setSubmitError('Title cannot exceed 120 characters.');
      return;
    }
    if (trimmedDesc.length < 10) {
      setSubmitError('Description must be at least 10 characters long.');
      return;
    }
    if (trimmedDesc.length > 2000) {
      setSubmitError('Description cannot exceed 2000 characters.');
      return;
    }
    if (!selectedDepartmentId) {
      setSubmitError('Please select a target campus department.');
      return;
    }

    setIsSubmitting(true);

    try {
      const savedRecord = await createComplaintApi({
        title: trimmedTitle,
        description: trimmedDesc,
        department_id: Number(selectedDepartmentId),
      });

      onSubmitSuccess(savedRecord);
    } catch (err: any) {
      if (err instanceof ApiClientError) {
        setSubmitError(err.message);
      } else {
        setSubmitError('Failed to register complaint. Please try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="complaint-form-wrapper">
      <div className="form-header">
        <h2>Register a Campus Complaint</h2>
        <p className="form-subtitle">
          Please provide factual, specific details. Once registered, your complaint is committed to the database and routed to the chosen department.
        </p>
      </div>

      {submitError && (
        <div className="form-error-banner" role="alert">
          {submitError}
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate>
        {/* Title Input */}
        <div className="form-group">
          <label htmlFor="complaint-title" className="field-label">
            <span>Complaint Title <span className="field-required">*</span></span>
            <span className="field-hint">3–120 characters</span>
          </label>
          <input
            id="complaint-title"
            type="text"
            className="text-input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Wi-Fi down in Lab 3 or Tap leaking in Hostel B"
            required
            maxLength={120}
            disabled={isSubmitting}
          />
          <div className="char-counter">{title.length} / 120</div>
        </div>

        {/* Description Textarea */}
        <div className="form-group" style={{ marginTop: 'var(--space-md)' }}>
          <label htmlFor="complaint-desc" className="field-label">
            <span>Detailed Description <span className="field-required">*</span></span>
            <span className="field-hint">10–2000 characters</span>
          </label>
          <textarea
            id="complaint-desc"
            className="text-area"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Provide exact room/location, timing, and nature of the grievance..."
            required
            rows={5}
            maxLength={2000}
            disabled={isSubmitting}
          />
          <div className="char-counter">{description.length} / 2000</div>
        </div>

        {/* Advisory Department Suggestion Trigger & Card */}
        <div style={{ marginTop: 'var(--space-md)' }}>
          <button
            type="button"
            className="btn-secondary"
            style={{ fontSize: '0.85rem', padding: '6px 14px' }}
            onClick={handleRequestSuggestion}
            disabled={isSuggesting || isSubmitting}
          >
            {isSuggesting ? 'Checking complaint keywords...' : '💡 Get Department Recommendation'}
          </button>

          {suggestionNotice && (
            <p style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', marginTop: '6px' }}>
              {suggestionNotice}
            </p>
          )}

          {suggestion && showSuggestion && (
            <div className="advisory-card" style={{ marginTop: 'var(--space-sm)' }}>
              <div className="advisory-header">
                <span className="advisory-title-badge">Advisory Suggestion (Non-Binding)</span>
                <span className="advisory-confidence-label">
                  Confidence: {Math.round(suggestion.confidence_score * 100)}%
                </span>
              </div>
              <div className="advisory-body">
                The keyword-based suggestion recommends routing this to:{' '}
                <span className="advisory-highlight">{suggestion.department_name}</span>.
                {suggestion.rationale && (
                  <p style={{ marginTop: '4px', fontSize: '0.85rem' }}>{suggestion.rationale}</p>
                )}
              </div>
              <div className="advisory-actions">
                <button
                  type="button"
                  className="btn-advisory-accept"
                  onClick={handleAcceptSuggestion}
                >
                  Accept & Apply to Dropdown
                </button>
                <button
                  type="button"
                  className="btn-advisory-dismiss"
                  onClick={() => setShowSuggestion(false)}
                >
                  Dismiss / Choose Manually
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Department Selector */}
        <div className="form-group" style={{ marginTop: 'var(--space-lg)' }}>
          <label htmlFor="complaint-dept" className="field-label">
            <span>Department / Authority Responsible <span className="field-required">*</span></span>
          </label>

          {isLoadingDepts ? (
            <div style={{ padding: '12px', color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
              Loading active departments from server...
            </div>
          ) : deptLoadError ? (
            <div style={{ color: 'var(--color-error-text)', fontSize: '0.9rem' }}>
              {deptLoadError}{' '}
              <button
                type="button"
                onClick={loadDepartments}
                style={{ textDecoration: 'underline', background: 'none', border: 'none', cursor: 'pointer' }}
              >
                Retry
              </button>
            </div>
          ) : (
            <select
              id="complaint-dept"
              className="select-input"
              value={selectedDepartmentId}
              onChange={(e) => setSelectedDepartmentId(Number(e.target.value) || '')}
              required
              disabled={isSubmitting}
            >
              <option value="">-- Select Campus Department --</option>
              {departments.map((dept) => (
                <option key={dept.id} value={dept.id}>
                  {dept.name} {dept.description ? `— ${dept.description}` : ''}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Form Actions with duplicate submit prevention */}
        <div className="form-actions">
          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              setTitle('');
              setDescription('');
              setSelectedDepartmentId('');
              setSuggestion(null);
              setSubmitError(null);
            }}
            disabled={isSubmitting}
          >
            Clear Form
          </button>
          <button type="submit" className="btn-primary" disabled={isSubmitting || isLoadingDepts}>
            {isSubmitting ? 'Submitting to Database...' : 'Submit Complaint'}
          </button>
        </div>
      </form>
    </div>
  );
}
