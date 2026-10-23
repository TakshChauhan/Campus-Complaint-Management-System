/** Reusable CCMS UI primitives. Visual rules live in ui.css. */
import React, { useEffect, useId, useRef, useState } from 'react';
import { Icon, IconName } from './Icon';
import { Link } from '../../lib/router';
import { statusLabel } from '../../lib/format';
import './ui.css';

export { Icon } from './Icon';
export type { IconName } from './Icon';

// ------------------------------------------------------------------ Button

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

interface ButtonOwnProps {
  variant?: ButtonVariant;
  size?: 'md' | 'sm';
  icon?: IconName;
  /** Icon placed after the label (e.g. "Next"). */
  iconAfter?: IconName;
  loading?: boolean;
  block?: boolean;
}

type ButtonProps = ButtonOwnProps & React.ButtonHTMLAttributes<HTMLButtonElement>;

function buttonClass({ variant = 'primary', size = 'md', block }: ButtonOwnProps, extra?: string) {
  return ['btn', `btn--${variant}`, size === 'sm' && 'btn--sm', block && 'btn--block', extra].filter(Boolean).join(' ');
}

export function Button({ variant, size, icon, iconAfter, loading, block, className, children, disabled, type = 'button', ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      className={buttonClass({ variant, size, block }, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Spinner size={16} /> : icon ? <Icon name={icon} size={18} /> : null}
      <span>{children}</span>
      {iconAfter && !loading ? <Icon name={iconAfter} size={18} /> : null}
    </button>
  );
}

type ButtonLinkProps = ButtonOwnProps & { to: string; children: React.ReactNode; className?: string };

export function ButtonLink({ to, variant, size, icon, block, className, children }: ButtonLinkProps) {
  return (
    <Link to={to} className={buttonClass({ variant, size, block }, className)}>
      {icon ? <Icon name={icon} size={18} /> : null}
      <span>{children}</span>
    </Link>
  );
}

// ------------------------------------------------------------------ Spinner / Skeleton

export function Spinner({ size = 20, label }: { size?: number; label?: string }) {
  return (
    <span className="spinner" style={{ width: size, height: size }} role={label ? 'status' : undefined}>
      {label ? <span className="visually-hidden">{label}</span> : null}
    </span>
  );
}

export function Skeleton({ width = '100%', height = 14, className }: { width?: string | number; height?: number; className?: string }) {
  return <span className={['skeleton', className].filter(Boolean).join(' ')} style={{ width, height }} aria-hidden="true" />;
}

// ------------------------------------------------------------------ Alert

type AlertTone = 'error' | 'success' | 'info' | 'warning';

const ALERT_ICON: Record<AlertTone, IconName> = {
  error: 'alert',
  success: 'check',
  info: 'info',
  warning: 'alert',
};

interface AlertProps {
  tone?: AlertTone;
  title?: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export function Alert({ tone = 'info', title, children, action, className }: AlertProps) {
  const role = tone === 'error' ? 'alert' : 'status';
  return (
    <div className={['alert', `alert--${tone}`, className].filter(Boolean).join(' ')} role={role}>
      <Icon name={ALERT_ICON[tone]} size={20} className="alert__icon" />
      <div className="alert__body">
        {title ? <p className="alert__title">{title}</p> : null}
        {children ? <div className="alert__text">{children}</div> : null}
      </div>
      {action ? <div className="alert__action">{action}</div> : null}
    </div>
  );
}

// ------------------------------------------------------------------ Form fields

interface FieldShellProps {
  id: string;
  label: string;
  required?: boolean;
  hint?: React.ReactNode;
  error?: string | null;
  counter?: { value: number; max: number };
  children: React.ReactNode;
}

function FieldShell({ id, label, required, hint, error, counter, children }: FieldShellProps) {
  return (
    <div className={['field', error && 'field--invalid'].filter(Boolean).join(' ')}>
      <div className="field__labelrow">
        <label htmlFor={id} className="field__label">
          {label}
          {required ? (
            <span className="field__required" aria-hidden="true">
              {' '}*
            </span>
          ) : (
            <span className="field__optional"> (optional)</span>
          )}
        </label>
        {counter ? (
          <span
            className={['field__counter', counter.value > counter.max && 'field__counter--over'].filter(Boolean).join(' ')}
            aria-live="polite"
          >
            {counter.value}/{counter.max}
          </span>
        ) : null}
      </div>
      {children}
      {error ? (
        <p className="field__error" id={`${id}-error`}>
          <Icon name="alert" size={16} />
          {error}
        </p>
      ) : hint ? (
        <p className="field__hint" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

function describedBy(id: string, error?: string | null, hint?: React.ReactNode) {
  if (error) return `${id}-error`;
  if (hint) return `${id}-hint`;
  return undefined;
}

type InputProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, 'id'> & {
  label: string;
  hint?: React.ReactNode;
  error?: string | null;
  showCounter?: boolean;
  trailing?: React.ReactNode;
};

export const TextField = React.forwardRef<HTMLInputElement, InputProps>(function TextField(
  { label, hint, error, required, showCounter, maxLength, trailing, value, className, ...rest },
  ref,
) {
  const id = useId();
  const counter = showCounter && maxLength ? { value: String(value ?? '').length, max: maxLength } : undefined;
  return (
    <FieldShell id={id} label={label} required={required} hint={hint} error={error} counter={counter}>
      <div className={['input-wrap', trailing && 'input-wrap--trailing'].filter(Boolean).join(' ')}>
        <input
          ref={ref}
          id={id}
          className={['input', className].filter(Boolean).join(' ')}
          value={value}
          maxLength={maxLength}
          required={required}
          aria-required={required || undefined}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(id, error, hint)}
          {...rest}
        />
        {trailing}
      </div>
    </FieldShell>
  );
});

type TextAreaProps = Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, 'id'> & {
  label: string;
  hint?: React.ReactNode;
  error?: string | null;
  showCounter?: boolean;
};

export const TextAreaField = React.forwardRef<HTMLTextAreaElement, TextAreaProps>(function TextAreaField(
  { label, hint, error, required, showCounter, maxLength, value, ...rest },
  ref,
) {
  const id = useId();
  const counter = showCounter && maxLength ? { value: String(value ?? '').length, max: maxLength } : undefined;
  return (
    <FieldShell id={id} label={label} required={required} hint={hint} error={error} counter={counter}>
      <textarea
        ref={ref}
        id={id}
        className="input input--textarea"
        value={value}
        maxLength={maxLength}
        required={required}
        aria-required={required || undefined}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, error, hint)}
        {...rest}
      />
    </FieldShell>
  );
});

type SelectProps = Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'id'> & {
  label: string;
  hint?: React.ReactNode;
  error?: string | null;
};

export const SelectField = React.forwardRef<HTMLSelectElement, SelectProps>(function SelectField(
  { label, hint, error, required, children, ...rest },
  ref,
) {
  const id = useId();
  return (
    <FieldShell id={id} label={label} required={required} hint={hint} error={error}>
      <div className="select-wrap">
        <select
          ref={ref}
          id={id}
          className="input input--select"
          required={required}
          aria-required={required || undefined}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(id, error, hint)}
          {...rest}
        >
          {children}
        </select>
      </div>
    </FieldShell>
  );
});

/** Password input with a working show/hide toggle. */
export const PasswordField = React.forwardRef<HTMLInputElement, Omit<InputProps, 'type' | 'trailing'>>(
  function PasswordField(props, ref) {
    const [visible, setVisible] = useState(false);
    return (
      <TextField
        ref={ref}
        {...props}
        type={visible ? 'text' : 'password'}
        trailing={
          <button
            type="button"
            className="input-toggle"
            onClick={() => setVisible((v) => !v)}
            aria-label={visible ? 'Hide password' : 'Show password'}
            aria-pressed={visible}
          >
            <Icon name={visible ? 'eyeOff' : 'eye'} size={18} />
          </button>
        }
      />
    );
  },
);

// ------------------------------------------------------------------ Status badge

export function StatusBadge({ status }: { status: string }) {
  const tone = ['submitted', 'in_progress', 'resolved', 'rejected', 'closed', 'reopened'].includes(status) ? status : 'other';
  return (
    <span className={`status status--${tone}`}>
      <span className="status__dot" aria-hidden="true" />
      {statusLabel(status)}
    </span>
  );
}

// ------------------------------------------------------------------ Copy button

export function CopyButton({ value, label = 'Copy' }: { value: string; label?: string }) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle');
  const timer = useRef<number | null>(null);
  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current);
  }, []);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setState('copied');
    } catch {
      setState('failed');
    }
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState('idle'), 2000);
  };

  return (
    <button type="button" className="copy-btn" onClick={copy} aria-label={`${label} ${value}`}>
      <Icon name={state === 'copied' ? 'check' : 'copy'} size={16} />
      <span aria-live="polite">{state === 'copied' ? 'Copied' : state === 'failed' ? 'Copy failed' : label}</span>
    </button>
  );
}

// ------------------------------------------------------------------ Panels & empty states

export function Panel({
  title,
  action,
  children,
  className,
  as: Tag = 'section',
}: {
  title?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  as?: 'section' | 'div' | 'article';
}) {
  return (
    <Tag className={['panel', className].filter(Boolean).join(' ')}>
      {title || action ? (
        <header className="panel__head">
          {title ? <h2 className="panel__title">{title}</h2> : <span />}
          {action}
        </header>
      ) : null}
      {children}
    </Tag>
  );
}

export function EmptyState({
  icon = 'inbox',
  title,
  children,
  action,
}: {
  icon?: IconName;
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty__icon">
        <Icon name={icon} size={28} />
      </span>
      <h3 className="empty__title">{title}</h3>
      {children ? <div className="empty__text">{children}</div> : null}
      {action ? <div className="empty__action">{action}</div> : null}
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <h1 className="page-header__title">{title}</h1>
        {description ? <p className="page-header__desc">{description}</p> : null}
      </div>
      {actions ? <div className="page-header__actions">{actions}</div> : null}
    </header>
  );
}

/** Label/value rows for detail views. */
export function DetailList({ items }: { items: { label: string; value: React.ReactNode }[] }) {
  return (
    <dl className="detail-list">
      {items.map((item) => (
        <div className="detail-list__row" key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
