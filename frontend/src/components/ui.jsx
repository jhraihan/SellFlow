import { Inbox } from "lucide-react";
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

export function PageLoader({ label = "Loading" }) {
  return (
    <div className="flex items-center justify-center gap-3 py-24 text-muted">
      <Spinner className="h-4 w-4 text-olive" />
      <span className="text-sm font-medium">{label}...</span>
    </div>
  );
}

const HEADER_TONES = {
  plain: {
    box: "",
    eyebrow: "text-muted",
    dot: "bg-butter-deep",
    title: "text-ink",
    note: "text-muted",
    glow: null,
  },
  white: {
    box: "border border-line/80 bg-white shadow-soft px-6 py-7 lg:px-9 lg:py-9",
    eyebrow: "text-muted",
    dot: "bg-butter-deep",
    title: "text-ink",
    note: "text-muted",
    glow: "bg-butter/40",
  },
  butter: {
    box: "bg-butter px-6 py-7 lg:px-9 lg:py-9",
    eyebrow: "text-ink/55",
    dot: "bg-ink",
    title: "text-ink",
    note: "text-ink/65",
    glow: "bg-white/50",
  },
  olive: {
    box: "bg-gradient-to-br from-olive to-olive-deep px-6 py-7 text-paper lg:px-9 lg:py-9",
    eyebrow: "text-paper/60",
    dot: "bg-butter",
    title: "text-paper",
    note: "text-paper/70",
    glow: "bg-butter/25",
  },
  sand: {
    box: "bg-sand px-6 py-7 lg:px-9 lg:py-9",
    eyebrow: "text-olive/75",
    dot: "bg-olive",
    title: "text-ink",
    note: "text-olive",
    glow: "bg-white/60",
  },
  clay: {
    box: "bg-clay-soft px-6 py-7 lg:px-9 lg:py-9",
    eyebrow: "text-[#8A6446]",
    dot: "bg-clay",
    title: "text-ink",
    note: "text-[#8A6446]",
    glow: "bg-white/60",
  },
};

export function PageHeader({ eyebrow, title, note, actions, aside, tone = "plain", icon: Icon, children }) {
  const t = HEADER_TONES[tone] || HEADER_TONES.plain;
  return (
    <header className={`relative ${t.box ? "overflow-hidden rounded-3xl" : ""} ${t.box}`}>
      {t.glow && (
        <>
          <span className={`pointer-events-none absolute -right-16 -top-24 h-64 w-64 rounded-full blur-3xl ${t.glow}`} />
          <span className={`pointer-events-none absolute -bottom-28 right-1/3 h-48 w-48 rounded-full blur-3xl ${t.glow}`} />
        </>
      )}
      <div className="relative flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          {eyebrow && (
            <p className={`flex items-center gap-2 text-[11px] font-bold uppercase tracking-eyebrow ${t.eyebrow}`}>
              {Icon ? <Icon className="h-3.5 w-3.5" strokeWidth={2.5} /> : <span className={`h-1.5 w-1.5 rounded-full ${t.dot}`} />}
              {eyebrow}
            </p>
          )}
          <h1 className={`mt-3 text-[2rem] font-extrabold leading-[1.05] tracking-[-0.035em] lg:text-[2.75rem] ${t.title}`}>
            {title}
          </h1>
          {note && <p className={`mt-2 max-w-xl text-[15px] font-medium ${t.note}`}>{note}</p>}
        </div>
        {(aside || actions) && (
          <div className="flex flex-col items-start gap-4 lg:items-end">
            {aside}
            {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
          </div>
        )}
      </div>
      {children && <div className="relative mt-6">{children}</div>}
    </header>
  );
}

export function Figure({ value }) {
  if (typeof value === "string" && value.startsWith("৳")) {
    return (
      <span className="whitespace-nowrap">
        <span className="mr-[0.15em] align-[0.3em] text-[0.5em] font-semibold opacity-55">
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
    <div className="lg:text-right">
      <p className={`text-5xl font-extrabold leading-none tracking-[-0.04em] tabular-nums lg:text-6xl ${tone}`}>
        <Figure value={value} />
      </p>
      {label && <p className={`mt-2 text-xs font-medium ${labelTone}`}>{label}</p>}
    </div>
  );
}

export function StatusBadge({ status }) {
  const cls = ORDER_STATUS_CLASSES[status] || "bg-stone-100 text-stone-500 border-stone-200";
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${cls}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
      {ORDER_STATUS_LABELS[status] || status}
    </span>
  );
}

export function RiskBadge({ level }) {
  if (!level) return null;
  const cls = RISK_CLASSES[level] || RISK_CLASSES.good;
  return (
    <span className={`inline-flex whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-semibold ${cls}`}>
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
    <div className={`rounded-xl border px-4 py-3 text-sm ${tones[tone]}`} role="alert">
      <div className="flex items-start justify-between gap-3">
        <div>
          {title && <p className="font-bold">{title}</p>}
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

export function EmptyState({ title, description, action, icon: Icon = Inbox }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-sand-deep bg-white/70 px-6 py-16 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-butter-soft text-olive-deep ring-8 ring-butter-soft/40">
        <Icon className="h-6 w-6" strokeWidth={1.75} />
      </span>
      <h3 className="mt-5 text-xl font-bold tracking-tight text-ink">{title}</h3>
      {description && <p className="mt-1.5 max-w-sm text-sm text-muted">{description}</p>}
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

const ACCENTS = {
  butter: "bg-butter text-ink",
  olive: "bg-olive text-paper",
  sage: "bg-[#DDEAD9] text-ok",
  clay: "bg-clay-soft text-danger",
  sky: "bg-[#E1EAF2] text-[#34506A]",
  sand: "bg-sand text-olive-deep",
};

export function StatCard({ label, value, sub, tone, icon: Icon, accent = "sand", surface = "white" }) {
  const tones = {
    ok: "text-ok",
    warn: "text-warn",
    danger: "text-danger",
  };
  const surfaces = {
    white: "border border-line/80 bg-white shadow-soft",
    butter: "bg-butter",
    sand: "bg-sand",
    olive: "bg-olive text-paper",
  };
  const onDark = surface === "olive";
  return (
    <div className={`group flex min-w-0 flex-col justify-between rounded-2xl p-5 transition duration-300 hover:-translate-y-0.5 hover:shadow-lift ${surfaces[surface]}`}>
      <div className="flex items-start justify-between gap-3">
        <p className={`text-[13px] font-semibold ${onDark ? "text-paper/70" : "text-ink/60"}`}>{label}</p>
        {Icon && (
          <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition group-hover:scale-110 ${ACCENTS[accent]}`}>
            <Icon className="h-[18px] w-[18px]" strokeWidth={2} />
          </span>
        )}
      </div>
      <div className="mt-5">
        <p className={`break-words text-[2rem] font-extrabold leading-none tracking-[-0.035em] tabular-nums ${
          tones[tone] || (onDark ? "text-paper" : "text-ink")
        }`}>
          <Figure value={value} />
        </p>
        {sub && (
          <p className={`mt-2 text-xs font-medium ${onDark ? "text-paper/60" : "text-muted"}`}>{sub}</p>
        )}
      </div>
    </div>
  );
}

export function Panel({ eyebrow, title, action, children, className = "", tone = "white", icon: Icon }) {
  const tones = {
    white: "border border-line/80 bg-white shadow-soft",
    sand: "bg-sand",
    butter: "bg-butter",
    paper: "border border-line bg-paper",
  };
  return (
    <section className={`rounded-2xl p-5 lg:p-6 ${tones[tone]} ${className}`}>
      {(title || eyebrow || action) && (
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            {Icon && (
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-ink text-butter">
                <Icon className="h-[18px] w-[18px]" strokeWidth={2} />
              </span>
            )}
            <div>
              {eyebrow && <p className="eyebrow">{eyebrow}</p>}
              {title && <h2 className="section-title mt-0.5">{title}</h2>}
            </div>
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
      <div className="absolute inset-0 bg-olive-deep/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl shadow-olive-deep/25">
        <div className="flex items-center justify-between border-b border-line px-6 py-4">
          <h2 className="text-lg font-bold tracking-tight">{title}</h2>
          <button type="button" onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-xl leading-none text-muted hover:bg-paper hover:text-ink"
            aria-label="Close">&times;</button>
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
