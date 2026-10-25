import React from "react";
import { DuplicateComplaintItem } from "../types";
import { Button, Icon, StatusBadge } from "./ui";
import { formatSimilarityScore } from "../lib/format";

interface DuplicateComplaintWarningProps {
  matches: DuplicateComplaintItem[];
  onSubmitAnyway: () => void;
  onDismiss: () => void;
  submitting?: boolean;
}

export function DuplicateComplaintWarning({
  matches,
  onSubmitAnyway,
  onDismiss,
  submitting = false,
}: DuplicateComplaintWarningProps) {
  if (!matches || matches.length === 0) return null;

  return (
    <div className="duplicate-warning" role="region" aria-label="Possible duplicate complaints warning">
      <div className="duplicate-warning__header">
        <div className="duplicate-warning__title-row">
          <span className="duplicate-warning__icon" aria-hidden="true">
            <Icon name="alert" size={20} />
          </span>
          <h3 className="duplicate-warning__title">
            Similar complaints already reported ({matches.length})
          </h3>
        </div>
        <p className="duplicate-warning__subtitle">
          Other campus members have submitted similar issues. Review these before submitting to avoid duplicate tickets.
        </p>
      </div>

      <ul className="duplicate-warning__list">
        {matches.map((item) => (
          <li key={item.id} className="duplicate-warning__item">
            <div className="duplicate-warning__item-main">
              <span className="duplicate-warning__item-title">{item.title}</span>
              <div className="duplicate-warning__item-meta">
                <span className="duplicate-warning__dept">{item.department_name}</span>
                <StatusBadge status={item.status} />
              </div>
              {item.description_snippet ? (
                <p className="duplicate-warning__snippet">{item.description_snippet}</p>
              ) : null}
            </div>
            <div className="duplicate-warning__score" title="Estimated similarity based on TF-IDF matching">
              <span className="duplicate-warning__score-value">{formatSimilarityScore(item.similarity_score)}</span>
              <span className="duplicate-warning__score-label">similarity</span>
            </div>
          </li>
        ))}
      </ul>

      <div className="duplicate-warning__actions">
        <Button
          variant="secondary"
          size="sm"
          onClick={onSubmitAnyway}
          disabled={submitting}
        >
          Submit anyway
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onDismiss}
          disabled={submitting}
        >
          Keep editing
        </Button>
      </div>
    </div>
  );
}
