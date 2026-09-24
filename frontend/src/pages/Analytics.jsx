import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, downloadFile } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money, moneyShort } from "@/lib/format";
import { Alert, EmptyState, PageLoader, StatCard } from "@/components/ui";

const RANGES = [
  ["7", "7 days"],
  ["30", "30 days"],
  ["90", "90 days"],
];

function rangeParams(days) {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - (Number(days) - 1));
  const iso = (d) => d.toISOString().slice(0, 10);
  return `date_from=${iso(start)}&date_to=${iso(end)}`;
}

export default function Analytics() {
  const { storeId, can } = useAuth();
  const [days, setDays] = useState("30");
  const params = rangeParams(days);

  const { data: profit, isLoading, error } = useQuery({
    queryKey: ["profit", storeId, days],
    queryFn: async () => (await api.get(`/analytics/profit/?${params}`)).data,
    enabled: Boolean(storeId) && can("view_analytics"),
  });

  const { data: products } = useQuery({
    queryKey: ["product-report", storeId, days],
    queryFn: async () => (await api.get(`/analytics/products/?${params}`)).data,
    enabled: Boolean(storeId) && can("view_analytics"),
  });

  const { data: couriers } = useQuery({
    queryKey: ["courier-report", storeId, days],
    queryFn: async () => (await api.get(`/analytics/couriers/?${params}`)).data,
    enabled: Boolean(storeId) && can("view_analytics"),
  });

  const { data: districts } = useQuery({
    queryKey: ["district-report", storeId, days],
    queryFn: async () => (await api.get(`/analytics/districts/?${params}`)).data,
    enabled: Boolean(storeId) && can("view_analytics"),
  });

  if (!can("view_analytics")) {
    return <EmptyState title="Not available for your role"
      description="Analytics is limited to owners, managers and accountants." />;
  }

  if (isLoading) return <PageLoader label="Crunching the numbers" />;
  if (error) return <Alert>Could not load the reports.</Alert>;

  const productRows = (products?.products || []).slice(0, 8);
  const chartData = productRows.map((row) => ({
    name: row.product_name.length > 14
      ? `${row.product_name.slice(0, 14)}...`
      : row.product_name,
    margin: Number(row.margin || 0),
  }));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Analytics</h1>
          <p className="text-sm text-muted">
            Revenue counts on delivery, never on the order.
          </p>
        </div>
        <div className="flex gap-2">
          {RANGES.map(([value, label]) => (
            <button key={value} type="button" onClick={() => setDays(value)}
              className={`rounded-full border px-3 py-1 text-sm ${
                days === value
                  ? "border-brand-600 bg-brand-50 font-medium text-brand-700"
                  : "border-line bg-white text-muted hover:text-ink"
              }`}>
              {label}
            </button>
          ))}
        </div>
      </div>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Net sales" value={money(profit?.net_sales)}
          sub={`${profit?.delivered_orders ?? 0} delivered orders`} />
        <StatCard label="Gross profit" value={money(profit?.gross_profit)} />
        <StatCard label="Net profit" value={money(profit?.net_profit)}
          tone={Number(profit?.net_profit) >= 0 ? "ok" : "danger"}
          sub={`${profit?.net_margin_percent ?? 0}% margin`} />
        <StatCard label="Return loss" value={money(profit?.return_loss)}
          tone={Number(profit?.return_loss) > 0 ? "danger" : undefined}
          sub={`${profit?.return_breakdown?.count ?? 0} returns`} />
      </section>

      <section className="card p-4">
        <h2 className="mb-3 text-sm font-semibold">How the profit is worked out</h2>
        <dl className="space-y-1.5 text-sm">
          <Row label="Gross sales" value={money(profit?.gross_sales)} />
          <Row label="Discounts given" value={`- ${money(profit?.discounts)}`} />
          <Row label="Net sales" value={money(profit?.net_sales)} strong />
          <Row label="Delivery charged to customers"
            value={`+ ${money(profit?.delivery_revenue)}`} />
          <Row label="Cost of goods sold" value={`- ${money(profit?.cogs)}`} />
          <Row label="Paid to couriers" value={`- ${money(profit?.delivery_cost)}`} />
          <Row label="Gross profit" value={money(profit?.gross_profit)} strong />
          <Row label="Lost to returns" value={`- ${money(profit?.return_loss)}`} />
          <Row label="Operating expenses"
            value={`- ${money(profit?.operating_expenses)}`} />
          <div className="flex items-baseline justify-between border-t border-line pt-2">
            <dt className="font-semibold">Net profit</dt>
            <dd className={`text-lg font-semibold tabular-nums ${
              Number(profit?.net_profit) >= 0 ? "text-ok" : "text-danger"
            }`}>{money(profit?.net_profit)}</dd>
          </div>
        </dl>
      </section>

      {chartData.length > 0 && (
        <section className="card p-4">
          <h2 className="mb-3 text-sm font-semibold">Margin by product</h2>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 10 }}
                  tickLine={false} axisLine={false} interval={0} angle={-20}
                  textAnchor="end" height={50} />
                <YAxis tickFormatter={moneyShort} tick={{ fontSize: 11 }}
                  tickLine={false} axisLine={false} width={60} />
                <Tooltip formatter={(value) => money(value)}
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #E2E8F0" }} />
                <Bar dataKey="margin" fill="#2563EB" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Products" empty="No delivered orders in this period."
          rows={productRows} exportKey="products"
          render={(row) => (
            <li key={row.product_id} className="flex justify-between gap-3 py-1.5 text-sm">
              <span className="min-w-0 truncate">{row.product_name}</span>
              <span className="shrink-0 tabular-nums">
                {row.units} sold &middot; {money(row.margin)} margin
                {Number(row.return_rate) > 0 && (
                  <span className="ml-2 text-danger">{row.return_rate}% back</span>
                )}
              </span>
            </li>
          )} />

        <Panel title="Couriers" empty="No shipments in this period."
          rows={couriers?.couriers || []} exportKey="couriers"
          render={(row) => (
            <li key={row.store_courier_id}
              className="flex justify-between gap-3 py-1.5 text-sm">
              <span className="min-w-0 truncate">
                {row.store_courier__courier__name}
              </span>
              <span className="shrink-0 tabular-nums">
                {row.shipped} parcels &middot; {row.success_rate}% delivered
                {Number(row.return_rate) > 0 && (
                  <span className="ml-2 text-danger">{row.return_rate}% back</span>
                )}
              </span>
            </li>
          )} />
      </div>

      <Panel title="Districts" empty="No orders in this period."
        rows={districts?.districts || []} exportKey="districts"
        render={(row) => (
          <li key={row.shipping_district}
            className="flex justify-between gap-3 py-1.5 text-sm">
            <span className="min-w-0 truncate">{row.shipping_district || "Unknown"}</span>
            <span className="shrink-0 tabular-nums">
              {row.total} orders &middot; {money(row.revenue)}
              {Number(row.return_rate) > 0 && (
                <span className="ml-2 text-danger">{row.return_rate}% back</span>
              )}
            </span>
          </li>
        )} />
    </div>
  );
}

function Row({ label, value, strong }) {
  return (
    <div className="flex items-baseline justify-between">
      <dt className={strong ? "font-medium" : "text-muted"}>{label}</dt>
      <dd className={`tabular-nums ${strong ? "font-medium" : ""}`}>{value}</dd>
    </div>
  );
}

function Panel({ title, rows, render, empty, exportKey }) {
  return (
    <section className="card p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold">{title}</h2>
        {rows.length > 0 && (
          <button type="button" className="text-xs text-brand-600 hover:underline"
            onClick={() => downloadFile(`/analytics/export/?report=${exportKey}`,
              `${exportKey}-report.csv`)}>
            Export CSV
          </button>
        )}
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">{empty}</p>
      ) : (
        <ul className="divide-y divide-line">{rows.map(render)}</ul>
      )}
    </section>
  );
}
