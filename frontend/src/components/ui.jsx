import { ORDER_STATUS_CLASSES, ORDER_STATUS_LABELS, RISK_CLASSES, RISK_LABELS } from "@/lib/format";

export function Spinner({ className = "h-5 w-5" }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
      <path className="opacity-80" fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  );
}

export function Brace({ children, className = "" }) {
  return (
    <span className={`font-display italic ${className}`}>
      {"{"}{children}{"}"}
    </span>
  );
}

export function PageLoader({ label = "Loading" }) {
  return (
    <div className="flex items-center justify-center gap-3 py-20 text-muted">
      <Spinner className="h-4 w-4" />
      <span className="font-display text-xl italic">{label}...</span>
    </div>
  );
}

const HEADER_TONES = {
  plain: {
    box: "pb-2",
    eyebrow: "text-muted",
    title: "text-ink",
    note: "text-muted",
  },
  white: {
    box: "border border-line bg-white px-6 py-8 lg:px-10 lg:py-10",
    eyebrow: "text-muted",
    title: "text-ink",
    note: "text-muted",
  },
  butter: {
    box: "bg-butter px-6 py-8 lg:px-10 lg:py-10",
    eyebrow: "text-ink/50",
    title: "text-ink",
    note: "text-ink/60",
  },
  olive: {
    box: "bg-olive px-6 py-8 text-paper lg:px-10 lg:py-10",
    eyebrow: "text-paper/55",
    title: "text-paper",
    note: "text-paper/65",
  },
  sand: {
    box: "bg-sand px-6 py-8 lg:px-10 lg:py-10",
    eyebrow: "text-olive/70",
    title: "text-ink",
    note: "text-olive",
  },
  clay: {
    box: "bg-clay-soft px-6 py-8 lg:px-10 lg:py-10",
    eyebrow: "text-clay",
    title: "text-ink",
    note: "text-[#8A6446]",
  },
};

export function PageHeader({ eyebrow, title, note, actions, aside, tone = "plain", children }) {
  const t = HEADER_TONES[tone] || HEADER_TONES.plain;
  return (
    <header className={`rounded-[4px] ${t.box}`}>
      <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          {eyebrow && (
            <p className={`text-[11px] font-medium uppercase tracking-eyebrow ${t.eyebrow}`}>
              {eyebrow}
            </p>
          )}
          <h1 className={`mt-2 font-display text-[2.6rem] font-normal leading-[0.95] tracking-tight lg:text-6xl ${t.title}`}>
            {title}
          </h1>
          {note && (
            <p className={`mt-3 font-display text-xl italic lg:text-2xl ${t.note}`}>
              {"{"}{note}{"}"}
            </p>
          )}
        </div>
        {(aside || actions) && (
          <div className="flex flex-col items-start gap-4 lg:items-end">
            {aside}
            {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
          </div>
        )}
      </div>
      {children && <div className="mt-6">{children}</div>}
    </header>
  );
}

export function Figure({ value }) {
  if (typeof value === "string" && value.startsWith("৳")) {
    return (
      <span className="whitespace-nowrap">
        <span className="mr-[0.12em] align-[0.35em] font-sans text-[0.42em] font-normal opacity-60">
          {"৳"}
        </span>
        {value.slice(1).trim()}
      </span>
    );
  }
  return value;
}

export function BigNumber({ value, label, tone = "text-ink", labelTone = "text-muted" }) {
  return (
    <div>
      <p className={`font-display text-6xl leading-none tabular-nums lg:text-7xl ${tone}`}><Figure value={value} /></p>
      {label && <p className={`mt-2 text-xs ${labelTone}`}>{label}</p>}
    </div>
  );
}

export function StatusBadge({ status }) {
  const cls = ORDER_STATUS_CLASSES[status] || "bg-stone-100 text-stone-500 border-stone-200";
  return (
    <span className={`inline-flex whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] font-medium tracking-wide ${cls}`}>
      {ORDER_STATUS_LABELS[status] || status}
    </span>
  );
}

export function RiskBadge({ level }) {
  if (!level) return null;
  const cls = RISK_CLASSES[level] || RISK_CLASSES.good;
  return (
    <span className={`inline-flex whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium tracking-wide ${cls}`}>
      {RISK_LABELS[level] || level}
    </span>
  );
}

export function Alert({ tone = "danger", title, children, onDismiss }) {
  const tones = {
    danger: "border-[#E3C6B6] bg-clay-soft text-[#7F2F1F]",
    warn: "border-butter-deep bg-butter-soft text-[#6B5410]",
    ok: "border-[#C8DBC5] bg-[#EEF4EC] text-[#35573A]",
    info: "border-sand-deep bg-sand text-olive-deep",
  };
  return (
    <div className={`rounded-[4px] border px-4 py-3 text-sm ${tones[tone]}`} role="alert">
      <div className="flex items-start justify-between gap-3">
        <div>
          {title && <p className="font-medium">{title}</p>}
          {children && <div className={title ? "mt-0.5" : ""}>{children}</div>}
        </div>
        {onDismiss && (
          <button type="button" onClick={onDismiss}
            className="shrink-0 text-lg leading-none opacity-50 hover:opacity-100" aria-label="Dismiss">
            &times;
          </button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-[4px] border border-dashed border-sand-deep bg-white/60 px-6 py-16 text-center">
      <h3 className="font-display text-3xl font-normal tracking-tight text-ink">{title}</h3>
      {description && <p className="mt-2 max-w-sm text-sm text-muted">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Field({ label, error, hint, required, children }) {
  return (
    <div>
      {label && (
        <label className="label">
          {label}
          {required && <span className="ml-0.5 text-clay">*</span>}
        </label>
      )}
      {children}
      {hint && !error && <p className="mt-1 text-xs text-muted">{hint}</p>}
      {error && <p className="field-error">{error}</p>}
    </div>
  );
}

export function StatCard({ label, value, sub, tone, surface = "white" }) {
  const tones = {
    ok: "text-ok",
    warn: "text-warn",
    danger: "text-danger",
  };
  const surfaces = {
    white: "border border-line bg-white",
    butter: "bg-butter",
    sand: "bg-sand",
    olive: "bg-olive text-paper",
  };
  const onDark = surface === "olive";
  return (
    <div className={`flex min-w-0 flex-col justify-between rounded-[4px] p-5 ${surfaces[surface]}`}>
      <p className={`text-[11px] font-medium uppercase tracking-eyebrow ${onDark ? "text-paper/55" : "text-muted"}`}>
        {label}
      </p>
      <div className="mt-6">
        <p className={`break-words font-display text-4xl leading-none tabular-nums xl:text-[2.75rem] ${
          tones[tone] || (onDark ? "text-paper" : "text-ink")
        }`}>
          <Figure value={value} />
        </p>
        {sub && (
          <p className={`mt-2 text-xs ${onDark ? "text-paper/60" : "text-muted"}`}>{sub}</p>
        )}
      </div>
    </div>
  );
}

export function Panel({ eyebrow, title, action, children, className = "", tone = "white" }) {
  const tones = {
    white: "border border-line bg-white",
    sand: "bg-sand",
    butter: "bg-butter",
    paper: "border border-line bg-paper",
  };
  return (
    <section className={`rounded-[4px] p-5 ${tones[tone]} ${className}`}>
      {(title || eyebrow || action) && (
        <div className="mb-4 flex items-end justify-between gap-3">
          <div>
            {eyebrow && <p className="eyebrow">{eyebrow}</p>}
            {title && <h2 className="section-title mt-1">{title}</h2>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Modal({ open, title, onClose, children, footer }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-olive-deep/50 backdrop-blur-[2px]" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg rounded-[4px] bg-white shadow-2xl shadow-olive-deep/20">
        <div className="flex items-center justify-between border-b border-line px-6 py-4">
          <h2 className="font-display text-2xl font-normal tracking-tight">{title}</h2>
          <button type="button" onClick={onClose}
            className="text-2xl leading-none text-muted hover:text-ink" aria-label="Close">&times;</button>
        </div>
        <div className="px-6 py-5">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 border-t border-line bg-paper/60 px-6 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
