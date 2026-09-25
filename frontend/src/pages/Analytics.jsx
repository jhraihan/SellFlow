import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, downloadFile } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money, moneyShort } from "@/lib/format";
import { Banknote, BarChart3, Download, PackageX, ShoppingBag, TrendingUp } from "lucide-react";
import { Alert, BigNumber, EmptyState, Figure, PageHeader, PageLoader, StatCard } from "@/components/ui";

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
      <PageHeader
        icon={BarChart3}
        tone="butter"
        eyebrow="Reports"
        title="Analytics"
        note="Revenue counts on delivery, never on the order"
        aside={<BigNumber value={money(profit?.net_profit)}
          tone={Number(profit?.net_profit) >= 0 ? "text-ink" : "text-danger"}
          labelTone="text-ink/60" label={`net profit, last ${days} days`} />}
      >
        <div className="flex gap-2">
          {RANGES.map(([value, label]) => (
            <button key={value} type="button" onClick={() => setDays(value)}
              className={`rounded-full border px-3.5 py-1 text-sm transition ${
                days === value
                  ? "border-ink bg-ink text-butter"
                  : "border-ink/20 text-ink/70 hover:border-ink/50 hover:text-ink"
              }`}>
              {label}
            </button>
          ))}
        </div>
      </PageHeader>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Net sales" icon={ShoppingBag} accent="butter" value={money(profit?.net_sales)}
          sub={`${profit?.delivered_orders ?? 0} delivered orders`} />
        <StatCard label="Gross profit" icon={TrendingUp} accent="sky" value={money(profit?.gross_profit)} />
        <StatCard label="Net profit" icon={Banknote} accent="sage" value={money(profit?.net_profit)}
          tone={Number(profit?.net_profit) >= 0 ? "ok" : "danger"}
          sub={`${profit?.net_margin_percent ?? 0}% margin`} />
        <StatCard label="Return loss" icon={PackageX} accent="clay" value={money(profit?.return_loss)}
          tone={Number(profit?.return_loss) > 0 ? "danger" : undefined}
          sub={`${profit?.return_breakdown?.count ?? 0} returns`} />
      </section>

      <section className="card grid gap-8 p-6 lg:grid-cols-[1fr_1.4fr] lg:p-8">
        <div>
          <p className="eyebrow">Profit statement</p>
          <h2 className="mt-2 text-2xl font-extrabold leading-tight tracking-[-0.03em]">
            How the profit is worked out
          </h2>
          <p className="mt-4 max-w-xs text-sm text-muted">
            Every figure comes from delivered orders in the period, after what the couriers
            charged and what came back.
          </p>
        </div>
        <dl className="space-y-2 text-sm">
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
          <div className="flex items-baseline justify-between border-t-2 border-ink pt-3">
            <dt className="text-lg font-bold">Net profit</dt>
            <dd className={`text-3xl font-extrabold tracking-[-0.035em] tabular-nums ${
              Number(profit?.net_profit) >= 0 ? "text-ok" : "text-danger"
            }`}><Figure value={money(profit?.net_profit)} /></dd>
          </div>
        </dl>
      </section>

      {chartData.length > 0 && (
        <section className="card p-4">
          <h2 className="mb-3 section-title">Margin by product</h2>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#EEE9DF" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 10 }}
                  tickLine={false} axisLine={false} interval={0} angle={-20}
                  textAnchor="end" height={50} />
                <YAxis tickFormatter={moneyShort} tick={{ fontSize: 11 }}
                  tickLine={false} axisLine={false} width={60} />
                <Tooltip formatter={(value) => money(value)}
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #E4DED2" }} />
                <Bar dataKey="margin" fill="#B98C66" radius={[2, 2, 0, 0]} maxBarSize={56} />
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
    <div className={`flex items-baseline justify-between ${strong ? "border-t border-line pt-2" : ""}`}>
      <dt className={strong ? "text-[15px] font-semibold" : "text-muted"}>{label}</dt>
      <dd className={`tabular-nums ${strong ? "text-[15px] font-semibold" : ""}`}>{value}</dd>
    </div>
  );
}

function Panel({ title, rows, render, empty, exportKey }) {
  return (
    <section className="card p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="section-title">{title}</h2>
        {rows.length > 0 && (
          <button type="button" className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1 text-xs font-semibold text-olive-deep transition hover:border-ink/30 hover:bg-paper"
            onClick={() => downloadFile(`/analytics/export/?report=${exportKey}`,
              `${exportKey}-report.csv`)}>
            <Download className="h-3.5 w-3.5" /> Export CSV
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
