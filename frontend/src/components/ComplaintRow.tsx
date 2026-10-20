import { Link } from '../lib/router';
import { ComplaintListItem } from '../types';
import { complaintReference, formatDate } from '../lib/format';
import { StatusBadge } from './ui';

/** One complaint in a list. The whole row links to the detail page. */
export function ComplaintRow({ item, compact = false }: { item: ComplaintListItem; compact?: boolean }) {
  return (
    <Link to={`/complaints/${item.id}`} className={['complaint-row', compact && 'complaint-row--compact'].filter(Boolean).join(' ')}>
      <div className="complaint-row__main">
        <div className="complaint-row__meta">
          <span className="complaint-row__ref">{complaintReference(item.id)}</span>
          <span className="complaint-row__dept">{item.department_name}</span>
        </div>
        <h3 className="complaint-row__title">{item.title}</h3>
        {!compact && item.description_preview ? <p className="complaint-row__preview">{item.description_preview}</p> : null}
      </div>
      <div className="complaint-row__side">
        <StatusBadge status={item.status} />
        <time className="complaint-row__date" dateTime={item.created_at}>
          {formatDate(item.created_at)}
        </time>
      </div>
    </Link>
  );
}
