import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money, moneyShort } from "@/lib/format";
import { Alert, EmptyState, PageLoader, StatCard } from "@/components/ui";

function Delta({ value }) {
  if (value === null || value === undefined) return null;
  const up = Number(value) >= 0;
  return (
    <span className={up ? "text-ok" : "text-danger"}>
      {up ? "+" : ""}{value}% vs yesterday
    </span>
  );
}

export default function Dashboard() {
  const { can, storeId } = useAuth();

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

  const chartData = (sales?.series || []).map((row) => ({
    date: new Date(row.date).toLocaleDateString("en-GB", { day: "2-digit", month: "short" }),
    sales: Number(row.net_sales || 0),
    orders: row.placed_orders,
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">Dashboard</h1>
        <p className="text-sm text-muted">Today at a glance.</p>
      </div>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Today's orders" value={today.orders ?? 0}
          sub={<Delta value={change.orders} />} />
        <StatCard label="Pending" value={data?.pending_confirmation ?? 0}
          tone={data?.pending_confirmation > 0 ? "warn" : undefined}
          sub="Awaiting confirmation" />
        <StatCard label="Delivered" value={today.delivered ?? 0}
          sub={<Delta value={change.delivered} />} />
        <StatCard label="Returned" value={today.returned ?? 0}
          tone={today.returned > 0 ? "danger" : undefined} sub="Today" />
      </section>

      <section className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <StatCard label="Today's sales" value={money(today.sales)}
          sub="Delivered orders only" />
        <StatCard label="Delivery cost" value={money(today.delivery_cost)} />
        <StatCard label="Net profit" value={money(today.net_profit)}
          tone={Number(today.net_profit) >= 0 ? "ok" : "danger"}
          sub="After costs and expenses" />
      </section>

      {chartData.length > 1 && (
        <section className="card p-4">
          <h2 className="mb-3 text-sm font-semibold">Sales, last 30 days</h2>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
                <defs>
                  <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#2563EB" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="#2563EB" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis tickFormatter={moneyShort} tick={{ fontSize: 11 }}
                  tickLine={false} axisLine={false} width={60} />
                <Tooltip formatter={(value) => money(value)}
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #E2E8F0" }} />
                <Area type="monotone" dataKey="sales" stroke="#2563EB"
                  strokeWidth={2} fill="url(#fill)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="card p-4">
          <h2 className="mb-3 text-sm font-semibold">Cash on delivery</h2>
          <dl className="space-y-2 text-sm">
            <Row label="In transit" value={money(cod.in_transit?.amount)}
              hint={`${cod.in_transit?.count ?? 0} parcels`} />
            <Row label="Collected, unsettled" value={money(cod.collected?.amount)}
              hint={`${cod.collected?.count ?? 0} parcels`} />
            <Row label="Overdue" value={money(cod.overdue?.amount)}
              hint={`${cod.overdue?.count ?? 0} parcels`}
              tone={cod.overdue?.count > 0 ? "danger" : undefined} />
          </dl>
          {can("reconcile_cod") && (
            <Link to="/payments" className="mt-3 inline-block text-sm text-brand-600 hover:underline">
              Open COD ledger
            </Link>
          )}
        </div>

        <div className="card p-4">
          <h2 className="mb-3 text-sm font-semibold">Low stock</h2>
          {data?.low_stock?.length ? (
            <ul className="space-y-2 text-sm">
              {data.low_stock.slice(0, 5).map((item) => (
                <li key={item.product_id} className="flex justify-between gap-2">
                  <span className="truncate">
                    {item.product_name}
                    {item.variant && <span className="text-muted"> ({item.variant})</span>}
                  </span>
                  <span className="shrink-0 font-medium text-warn">{item.available} left</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">Everything is above its threshold.</p>
          )}
        </div>

        <div className="card p-4">
          <h2 className="mb-3 text-sm font-semibold">Top products, 30 days</h2>
          {data?.top_products?.length ? (
            <ul className="space-y-2 text-sm">
              {data.top_products.map((row) => (
                <li key={row.product_id} className="flex justify-between gap-2">
                  <span className="truncate">{row.product_name}</span>
                  <span className="shrink-0 tabular-nums">{money(row.revenue)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">No delivered orders yet.</p>
          )}
        </div>
      </section>
    </div>
  );
}

function Row({ label, value, hint, tone }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-muted">
        {label}
        {hint && <span className="ml-1 text-xs">({hint})</span>}
      </dt>
      <dd className={`font-medium tabular-nums ${tone === "danger" ? "text-danger" : ""}`}>
        {value}
      </dd>
    </div>
  );
}
