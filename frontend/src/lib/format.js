export function money(value) {
  const number = Number(value ?? 0);
  if (Number.isNaN(number)) return "\u09F3 0";
  return `\u09F3 ${number.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function moneyShort(value) {
  const number = Number(value ?? 0);
  if (Number.isNaN(number)) return "\u09F3 0";
  if (Math.abs(number) >= 100000) {
    return `\u09F3 ${(number / 100000).toFixed(1)}L`;
  }
  if (Math.abs(number) >= 1000) {
    return `\u09F3 ${(number / 1000).toFixed(1)}k`;
  }
  return `\u09F3 ${number.toFixed(0)}`;
}

export function dateTime(value) {
  if (!value) return "";
  return new Date(value).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function dateOnly(value) {
  if (!value) return "";
  return new Date(value).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function relative(value) {
  if (!value) return "";
  const diff = Date.now() - new Date(value).getTime();
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return dateOnly(value);
}

export const ORDER_STATUS_LABELS = {
  pending: "Pending",
  confirmed: "Confirmed",
  processing: "Processing",
  ready_to_ship: "Ready to Ship",
  shipped: "Shipped",
  out_for_delivery: "Out for Delivery",
  delivered: "Delivered",
  cancelled: "Cancelled",
  returned: "Returned",
  on_hold: "On Hold",
};

export const ORDER_STATUS_CLASSES = {
  pending: "bg-amber-50 text-amber-700 border-amber-200",
  confirmed: "bg-blue-50 text-blue-700 border-blue-200",
  processing: "bg-indigo-50 text-indigo-700 border-indigo-200",
  ready_to_ship: "bg-violet-50 text-violet-700 border-violet-200",
  shipped: "bg-cyan-50 text-cyan-700 border-cyan-200",
  out_for_delivery: "bg-teal-50 text-teal-700 border-teal-200",
  delivered: "bg-emerald-50 text-emerald-700 border-emerald-200",
  cancelled: "bg-slate-100 text-slate-600 border-slate-200",
  returned: "bg-red-50 text-red-700 border-red-200",
  on_hold: "bg-orange-50 text-orange-700 border-orange-200",
};

export const RISK_CLASSES = {
  good: "bg-emerald-50 text-emerald-700 border-emerald-200",
  watch: "bg-amber-50 text-amber-700 border-amber-200",
  high_risk: "bg-red-50 text-red-700 border-red-200",
  blacklisted: "bg-slate-800 text-white border-slate-800",
};

export const RISK_LABELS = {
  good: "Good",
  watch: "Watch",
  high_risk: "High Risk",
  blacklisted: "Blacklisted",
};
