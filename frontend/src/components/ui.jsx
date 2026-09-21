import { ORDER_STATUS_CLASSES, ORDER_STATUS_LABELS, RISK_CLASSES, RISK_LABELS } from "@/lib/format";

export function Spinner({ className = "h-5 w-5" }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-80" fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  );
}

export function PageLoader({ label = "Loading" }) {
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-muted">
      <Spinner />
      <span className="text-sm">{label}...</span>
    </div>
  );
}

export function StatusBadge({ status }) {
  const cls = ORDER_STATUS_CLASSES[status] || "bg-slate-100 text-slate-600 border-slate-200";
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {ORDER_STATUS_LABELS[status] || status}
    </span>
  );
}

export function RiskBadge({ level }) {
  if (!level) return null;
  const cls = RISK_CLASSES[level] || RISK_CLASSES.good;
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${cls}`}>
      {RISK_LABELS[level] || level}
    </span>
  );
}

export function Alert({ tone = "danger", title, children, onDismiss }) {
  const tones = {
    danger: "border-red-200 bg-red-50 text-red-800",
    warn: "border-amber-200 bg-amber-50 text-amber-800",
    ok: "border-emerald-200 bg-emerald-50 text-emerald-800",
    info: "border-blue-200 bg-blue-50 text-blue-800",
  };
  return (
    <div className={`rounded-lg border px-4 py-3 text-sm ${tones[tone]}`} role="alert">
      <div className="flex items-start justify-between gap-3">
        <div>
          {title && <p className="font-medium">{title}</p>}
          {children && <div className={title ? "mt-0.5" : ""}>{children}</div>}
        </div>
        {onDismiss && (
          <button type="button" onClick={onDismiss}
            className="shrink-0 opacity-60 hover:opacity-100" aria-label="Dismiss">
            &times;
          </button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-line bg-white px-6 py-14 text-center">
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-sm text-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Field({ label, error, hint, required, children }) {
  return (
    <div>
      {label && (
        <label className="label">
          {label}
          {required && <span className="ml-0.5 text-danger">*</span>}
        </label>
      )}
      {children}
      {hint && !error && <p className="mt-1 text-xs text-muted">{hint}</p>}
      {error && <p className="field-error">{error}</p>}
    </div>
  );
}

export function StatCard({ label, value, sub, tone }) {
  const tones = {
    ok: "text-ok",
    warn: "text-warn",
    danger: "text-danger",
  };
  return (
    <div className="card p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${tones[tone] || "text-ink"}`}>
        {value}
      </p>
      {sub && <p className="mt-0.5 text-xs text-muted">{sub}</p>}
    </div>
  );
}

export function Modal({ open, title, onClose, children, footer }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/40" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          <button type="button" onClick={onClose}
            className="text-muted hover:text-ink" aria-label="Close">&times;</button>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 border-t border-line px-5 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
