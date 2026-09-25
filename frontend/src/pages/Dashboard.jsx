import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  ArrowRight, ArrowUpRight, Banknote, Boxes, PackageCheck, PackageX, Plus, ShoppingBag,
  Sparkles, TrendingDown, TrendingUp, Truck, Wallet,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money, moneyShort } from "@/lib/format";
import {
  Alert, BigNumber, EmptyState, Figure, PageHeader, PageLoader, Panel, StatCard,
} from "@/components/ui";

function Delta({ value }) {
  if (value === null || value === undefined) return <span>Compared with yesterday</span>;
  const up = Number(value) >= 0;
  const Icon = up ? TrendingUp : TrendingDown;
  return (
    <span className={`inline-flex items-center gap-1 font-semibold ${up ? "text-ok" : "text-danger"}`}>
      <Icon className="h-3.5 w-3.5" strokeWidth={2.5} />
      {up ? "+" : ""}{value}% vs yesterday
    </span>
  );
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function Dashboard() {
  const { can, storeId, stores, user } = useAuth();
  const storeName = stores.find((s) => s.store_id === storeId)?.store_name;
  const firstName = user?.full_name?.split(" ")[0] || "there";

  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard", storeId],
    queryFn: async () => (await api.get("/analytics/dashboard/")).data,
    enabled: Boolean(storeId) && can("view_analytics"),
  });

  const { data: sales } = useQuery({
    queryKey: ["sales-series", storeId],
    queryFn: async () => (await api.get("/analytics/sales/?group_by=day")).data,
    enabled: Boolean(storeId) && can("view_analytics"),
  });

  if (!can("view_analytics")) {
    return (
      <EmptyState
        title="No dashboard for your role"
        description="Your role does not include analytics. Head to Orders to start working."
        action={<Link to="/orders" className="btn-primary">Go to orders</Link>}
      />
    );
  }

  if (isLoading) return <PageLoader label="Loading your dashboard" />;
  if (error) return <Alert>Could not load the dashboard. Try refreshing.</Alert>;

  const today = data?.today || {};
  const change = data?.change || {};
  const cod = data?.cod || {};
  const pending = data?.pending_confirmation ?? 0;
  const profitUp = Number(today.net_profit) >= 0;
  const topMax = Math.max(1, ...(data?.top_products || []).map((row) => Number(row.revenue || 0)));

  const chartData = (sales?.series || []).map((row) => ({
    date: new Date(row.date).toLocaleDateString("en-GB", { day: "2-digit", month: "short" }),
    sales: Number(row.net_sales || 0),
    orders: row.placed_orders,
  }));

  return (
    <div className="space-y-6">
      <PageHeader
        tone="olive"
        icon={Sparkles}
        eyebrow={storeName || "Today at a glance"}
        title={`${greeting()}, ${firstName}`}
        note={pending > 0
          ? "Some customers are waiting on a confirmation call. Clear them first."
          : "You are all caught up. Here is how today is going."}
        aside={
          <BigNumber value={pending} tone="text-butter" labelTone="text-paper/65"
            label={pending === 1 ? "order awaiting confirmation" : "orders awaiting confirmation"} />
        }
        actions={
          pending > 0 ? (
            <Link to="/orders" className="btn-primary">
              Review orders <ArrowRight className="h-4 w-4" strokeWidth={2.5} />
            </Link>
          ) : (
            can("manage_orders") && (
              <Link to="/orders/new" className="btn-primary">
                <Plus className="h-4 w-4" strokeWidth={2.5} /> New order
              </Link>
            )
          )
        }
      />

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
        <StatCard label="Orders today" value={today.orders ?? 0} icon={ShoppingBag} accent="butter"
          sub={<Delta value={change.orders} />} />
        <StatCard label="Delivered" value={today.delivered ?? 0} icon={PackageCheck} accent="sage"
          sub={<Delta value={change.delivered} />} />
        <StatCard label="Returned" value={today.returned ?? 0} icon={PackageX} accent="clay"
          tone={today.returned > 0 ? "danger" : undefined} sub="Parcels back today" />
        <StatCard label="Delivery cost" value={money(today.delivery_cost)} icon={Truck} accent="sky"
          sub="Paid to couriers today" />
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="relative flex flex-col justify-between overflow-hidden rounded-2xl bg-gradient-to-br from-butter to-butter-deep p-6 shadow-glow">
          <span className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white/40 blur-2xl" />
          <div className="relative">
            <div className="flex items-center justify-between">
              <p className="text-[13px] font-bold text-ink/70">Net profit today</p>
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-ink text-butter">
                <Banknote className="h-[18px] w-[18px]" strokeWidth={2} />
              </span>
            </div>
            <p className={`mt-6 text-5xl font-extrabold leading-none tracking-[-0.04em] tabular-nums ${profitUp ? "text-ink" : "text-danger"}`}>
              <Figure value={money(today.net_profit)} />
            </p>
            <p className="mt-2 text-xs font-medium text-ink/65">After product cost, delivery and expenses</p>
          </div>
          <dl className="relative mt-8 space-y-2 rounded-xl bg-white/45 p-4 text-sm backdrop-blur">
            <div className="flex justify-between">
              <dt className="text-ink/70">Sales (delivered)</dt>
              <dd className="font-bold tabular-nums">{money(today.sales)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-ink/70">Delivery cost</dt>
              <dd className="font-bold tabular-nums">{money(today.delivery_cost)}</dd>
            </div>
          </dl>
        </div>

        <Panel eyebrow="Last 30 days" title="Sales trend" className="lg:col-span-2"
          action={can("view_analytics") && (
            <Link to="/analytics" className="inline-flex items-center gap-1 text-sm font-semibold text-olive hover:text-ink">
              Reports <ArrowUpRight className="h-4 w-4" />
            </Link>
          )}>
          {chartData.length > 1 ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -12, bottom: 0 }}>
                  <defs>
                    <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#EFD24F" stopOpacity={0.55} />
                      <stop offset="100%" stopColor="#EFD24F" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#EEE9DF" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#8B877A" }}
                    tickLine={false} axisLine={false} />
                  <YAxis tickFormatter={moneyShort} tick={{ fontSize: 11, fill: "#8B877A" }}
                    tickLine={false} axisLine={false} width={64} />
                  <Tooltip formatter={(value) => money(value)}
                    contentStyle={{ fontSize: 12, borderRadius: 12, border: "1px solid #E4DED2", boxShadow: "0 12px 30px -12px rgba(69,68,58,.3)" }} />
                  <Area type="monotone" dataKey="sales" stroke="#45443A"
                    strokeWidth={2.25} fill="url(#fill)" activeDot={{ r: 5, fill: "#EFD24F", stroke: "#45443A", strokeWidth: 2 }} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="flex h-64 flex-col items-center justify-center rounded-xl bg-paper/70 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-butter-soft text-olive-deep">
                <TrendingUp className="h-5 w-5" />
              </span>
              <p className="mt-3 text-sm font-semibold">Your chart starts here</p>
              <p className="mt-1 text-xs text-muted">It fills in as orders are delivered.</p>
            </div>
          )}
        </Panel>
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel tone="sand" icon={Wallet} eyebrow="Cash on delivery" title="Money on the road"
          action={can("reconcile_cod") && (
            <Link to="/payments" className="inline-flex items-center gap-1 text-sm font-semibold text-olive hover:text-ink">
              Ledger <ArrowUpRight className="h-4 w-4" />
            </Link>
          )}>
          <dl className="space-y-2">
            <Row label="In transit" value={money(cod.in_transit?.amount)}
              hint={`${cod.in_transit?.count ?? 0} parcels`} />
            <Row label="Collected, unsettled" value={money(cod.collected?.amount)}
              hint={`${cod.collected?.count ?? 0} parcels`} highlight />
            <Row label="Overdue" value={money(cod.overdue?.amount)}
              hint={`${cod.overdue?.count ?? 0} parcels`}
              tone={cod.overdue?.count > 0 ? "danger" : undefined} />
          </dl>
        </Panel>

        <Panel icon={Boxes} eyebrow="Inventory" title="Running low"
          action={
            <Link to="/products" className="inline-flex items-center gap-1 text-sm font-semibold text-olive hover:text-ink">
              Products <ArrowUpRight className="h-4 w-4" />
            </Link>
          }>
          {data?.low_stock?.length ? (
            <ul className="space-y-3">
              {data.low_stock.slice(0, 5).map((item) => (
                <li key={`${item.product_id}-${item.variant || ""}`}>
                  <div className="flex items-baseline justify-between gap-2 text-sm">
                    <span className="truncate font-semibold">
                      {item.product_name}
                      {item.variant && <span className="font-normal text-muted"> ({item.variant})</span>}
                    </span>
                    <span className="shrink-0 text-xs font-bold text-warn">{item.available} left</span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-paper">
                    <div className="h-full rounded-full bg-gradient-to-r from-clay to-butter-deep"
                      style={{ width: `${Math.max(6, Math.min(100, (item.available / Math.max(1, item.threshold || 10)) * 100))}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="flex items-center gap-3 rounded-xl bg-[#EEF4EC] p-4 text-sm text-[#35573A]">
              <PackageCheck className="h-5 w-5 shrink-0" />
              Everything is above its threshold.
            </div>
          )}
        </Panel>

        <Panel icon={TrendingUp} eyebrow="Best sellers, 30 days" title="Top products">
          {data?.top_products?.length ? (
            <ol className="space-y-3">
              {data.top_products.map((row, index) => (
                <li key={row.product_id}>
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="flex min-w-0 items-center gap-2.5">
                      <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[11px] font-extrabold ${
                        index === 0 ? "bg-butter text-ink" : "bg-paper text-muted"
                      }`}>{index + 1}</span>
                      <span className="truncate font-semibold">{row.product_name}</span>
                    </span>
                    <span className="shrink-0 font-bold tabular-nums">{money(row.revenue)}</span>
                  </div>
                  <div className="ml-8 mt-1.5 h-1.5 overflow-hidden rounded-full bg-paper">
                    <div className="h-full rounded-full bg-olive"
                      style={{ width: `${(Number(row.revenue || 0) / topMax) * 100}%` }} />
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-muted">No delivered orders yet.</p>
          )}
        </Panel>
      </section>
    </div>
  );
}

function Row({ label, value, hint, tone, highlight }) {
  return (
    <div className={`flex items-center justify-between gap-3 rounded-xl px-3.5 py-3 ${
      highlight ? "bg-white shadow-soft" : "bg-white/50"
    }`}>
      <dt>
        <p className="text-sm font-semibold text-ink/80">{label}</p>
        {hint && <p className="text-xs text-ink/50">{hint}</p>}
      </dt>
      <dd className={`text-lg font-extrabold tracking-tight tabular-nums ${tone === "danger" ? "text-danger" : ""}`}>
        <Figure value={value} />
      </dd>
    </div>
  );
}
