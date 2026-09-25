import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money, moneyShort } from "@/lib/format";
import {
  Alert, BigNumber, EmptyState, Figure, PageHeader, PageLoader, Panel, StatCard,
} from "@/components/ui";

function Delta({ value }) {
  if (value === null || value === undefined) return null;
  const up = Number(value) >= 0;
  return (
    <span className={up ? "text-ok" : "text-danger"}>
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

  const chartData = (sales?.series || []).map((row) => ({
    date: new Date(row.date).toLocaleDateString("en-GB", { day: "2-digit", month: "short" }),
    sales: Number(row.net_sales || 0),
    orders: row.placed_orders,
  }));

  return (
    <div className="space-y-6">
      <PageHeader
        tone="olive"
        eyebrow="Today at a glance"
        title={`${greeting()}, ${firstName}`}
        note={storeName}
        aside={
          <BigNumber value={pending} tone="text-butter" labelTone="text-paper/60"
            label={pending === 1 ? "order awaiting confirmation" : "orders awaiting confirmation"} />
        }
        actions={
          pending > 0 ? (
            <Link to="/orders" className="btn-primary">Review orders</Link>
          ) : (
            can("manage_orders") && <Link to="/orders/new" className="btn-primary">New order</Link>
          )
        }
      />

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Orders today" value={today.orders ?? 0}
          sub={<Delta value={change.orders} />} />
        <StatCard label="Delivered" value={today.delivered ?? 0}
          sub={<Delta value={change.delivered} />} />
        <StatCard label="Returned" value={today.returned ?? 0}
          tone={today.returned > 0 ? "danger" : undefined} sub="Today" />
        <StatCard label="Delivery cost" value={money(today.delivery_cost)} sub="Paid to couriers today" />
      </section>

      <section className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <div className="flex flex-col justify-between rounded-[4px] bg-butter p-6">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-eyebrow text-ink/50">Net profit today</p>
            <p className={`mt-6 font-display text-6xl leading-none tabular-nums ${profitUp ? "text-ink" : "text-danger"}`}>
              <Figure value={money(today.net_profit)} />
            </p>
            <p className="mt-2 text-xs text-ink/60">After product cost, delivery and expenses</p>
          </div>
          <dl className="mt-8 space-y-2 border-t border-ink/15 pt-4 text-sm">
            <div className="flex justify-between">
              <dt className="text-ink/60">Sales (delivered)</dt>
              <dd className="tabular-nums">{money(today.sales)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-ink/60">Delivery cost</dt>
              <dd className="tabular-nums">{money(today.delivery_cost)}</dd>
            </div>
          </dl>
        </div>

        <Panel eyebrow="Last 30 days" title="Sales" className="lg:col-span-2">
          {chartData.length > 1 ? (
            <div className="h-60">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -12, bottom: 0 }}>
                  <defs>
                    <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#F8E27A" stopOpacity={0.8} />
                      <stop offset="100%" stopColor="#F8E27A" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#EEE9DF" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#8B877A" }}
                    tickLine={false} axisLine={false} />
                  <YAxis tickFormatter={moneyShort} tick={{ fontSize: 11, fill: "#8B877A" }}
                    tickLine={false} axisLine={false} width={64} />
                  <Tooltip formatter={(value) => money(value)}
                    contentStyle={{ fontSize: 12, borderRadius: 4, border: "1px solid #E4DED2" }} />
                  <Area type="monotone" dataKey="sales" stroke="#5C5B4A"
                    strokeWidth={1.75} fill="url(#fill)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="py-16 text-center font-display text-xl italic text-muted">
              {"{The chart fills in as orders are delivered}"}
            </p>
          )}
        </Panel>
      </section>

      <section className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <Panel tone="sand" eyebrow="Cash on delivery" title="Money on the road"
          action={can("reconcile_cod") && <Link to="/payments" className="link text-sm">Ledger</Link>}>
          <dl className="divide-y divide-ink/10 text-sm">
            <Row label="In transit" value={money(cod.in_transit?.amount)}
              hint={`${cod.in_transit?.count ?? 0} parcels`} />
            <Row label="Collected, unsettled" value={money(cod.collected?.amount)}
              hint={`${cod.collected?.count ?? 0} parcels`} />
            <Row label="Overdue" value={money(cod.overdue?.amount)}
              hint={`${cod.overdue?.count ?? 0} parcels`}
              tone={cod.overdue?.count > 0 ? "danger" : undefined} />
          </dl>
        </Panel>

        <Panel eyebrow="Inventory" title="Running low"
          action={<Link to="/products" className="link text-sm">Products</Link>}>
          {data?.low_stock?.length ? (
            <ul className="divide-y divide-line">
              {data.low_stock.slice(0, 5).map((item) => (
                <li key={`${item.product_id}-${item.variant || ""}`}
                  className="flex items-baseline justify-between gap-2 py-2.5">
                  <span className="truncate font-display text-lg">
                    {item.product_name}
                    {item.variant && <span className="text-muted"> ({item.variant})</span>}
                  </span>
                  <span className="shrink-0 text-xs font-medium text-warn">{item.available} left</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">Everything is above its threshold.</p>
          )}
        </Panel>

        <Panel eyebrow="Best sellers, 30 days" title="Top products">
          {data?.top_products?.length ? (
            <ol className="divide-y divide-line">
              {data.top_products.map((row, index) => (
                <li key={row.product_id} className="flex items-baseline justify-between gap-3 py-2.5">
                  <span className="flex min-w-0 items-baseline gap-3">
                    <span className="font-display text-sm italic text-muted">0{index + 1}</span>
                    <span className="truncate font-display text-lg">{row.product_name}</span>
                  </span>
                  <span className="shrink-0 text-sm tabular-nums">{money(row.revenue)}</span>
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

function Row({ label, value, hint, tone }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-2.5">
      <dt className="text-ink/70">
        {label}
        {hint && <span className="ml-1 text-xs text-ink/45">({hint})</span>}
      </dt>
      <dd className={`font-display text-xl tabular-nums ${tone === "danger" ? "text-danger" : ""}`}>
        <Figure value={value} />
      </dd>
    </div>
  );
}
