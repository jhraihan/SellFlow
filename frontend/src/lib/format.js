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
  pending: "bg-butter-soft text-[#7A600E] border-butter-deep",
  confirmed: "bg-sand text-olive-deep border-sand-deep",
  processing: "bg-[#ECE8F1] text-[#4E4868] border-[#D8D2E4]",
  ready_to_ship: "bg-[#E5EEEC] text-[#355953] border-[#C9DAD6]",
  shipped: "bg-[#E4ECF2] text-[#34506A] border-[#CAD8E4]",
  out_for_delivery: "bg-[#E9F0E2] text-[#4A6540] border-[#D2DFC6]",
  delivered: "bg-[#E4EEE2] text-ok border-[#C8DBC5]",
  cancelled: "bg-stone-100 text-stone-500 border-stone-200",
  returned: "bg-clay-soft text-danger border-[#E3C6B6]",
  on_hold: "bg-[#F6E8D6] text-warn border-[#EBD1B0]",
};

export const RISK_CLASSES = {
  good: "bg-[#E4EEE2] text-ok border-[#C8DBC5]",
  watch: "bg-butter-soft text-[#7A600E] border-butter-deep",
  high_risk: "bg-clay-soft text-danger border-[#E3C6B6]",
  blacklisted: "bg-ink text-paper border-ink",
};

export const RISK_LABELS = {
  good: "Good",
  watch: "Watch",
  high_risk: "High Risk",
  blacklisted: "Blacklisted",
};
