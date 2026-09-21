import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money, relative } from "@/lib/format";
import { Alert, EmptyState, PageLoader, RiskBadge, StatusBadge } from "@/components/ui";

const FILTERS = [
  ["", "All"],
  ["pending", "Pending"],
  ["confirmed", "Confirmed"],
  ["ready_to_ship", "Ready"],
  ["shipped", "Shipped"],
  ["delivered", "Delivered"],
  ["returned", "Returned"],
];

export default function Orders() {
  const { can, storeId } = useAuth();
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["orders", storeId, status, query],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (query) params.set("search", query);
      return (await api.get(`/orders/?${params}`)).data;
    },
    enabled: Boolean(storeId),
  });

  function onSearch(event) {
    event.preventDefault();
    setQuery(search.trim());
  }

  const orders = data?.results || [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Orders</h1>
          <p className="text-sm text-muted">Confirm, track and ship.</p>
        </div>
        {can("manage_orders") && (
          <Link to="/orders/new" className="btn-primary">+ New Order</Link>
        )}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <form onSubmit={onSearch} className="flex flex-1 gap-2">
          <input className="input" placeholder="Order number, name or phone"
            value={search} onChange={(e) => setSearch(e.target.value)}
            aria-label="Search orders" />
          <button type="submit" className="btn-secondary">Search</button>
        </form>
      </div>

      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 lg:mx-0 lg:px-0">
        {FILTERS.map(([value, label]) => (
          <button key={value} type="button" onClick={() => setStatus(value)}
            className={`shrink-0 rounded-full border px-3 py-1 text-sm ${
              status === value
                ? "border-brand-600 bg-brand-50 font-medium text-brand-700"
                : "border-line bg-white text-muted hover:text-ink"
            }`}>
            {label}
          </button>
        ))}
      </div>

      {isLoading && <PageLoader label="Loading orders" />}
      {error && <Alert>Could not load orders. Try refreshing.</Alert>}

      {!isLoading && !error && orders.length === 0 && (
        <EmptyState
          title={query || status ? "No orders match" : "No orders yet"}
          description={
            query || status
              ? "Try a different search or filter."
              : "Take your first order and it will appear here."
          }
          action={
            can("manage_orders") && !query && !status ? (
              <Link to="/orders/new" className="btn-primary">Create an order</Link>
            ) : null
          }
        />
      )}

      {orders.length > 0 && (
        <>
          <div className="hidden overflow-hidden rounded-xl border border-line bg-white lg:block">
            <table className="w-full text-sm">
              <thead className="border-b border-line bg-surface text-left text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Order</th>
                  <th className="px-4 py-2.5 font-medium">Customer</th>
                  <th className="px-4 py-2.5 font-medium">District</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5 text-right font-medium">COD</th>
                  <th className="px-4 py-2.5 text-right font-medium">Placed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {orders.map((order) => (
                  <tr key={order.id} className="hover:bg-surface">
                    <td className="px-4 py-2.5">
                      <Link to={`/orders/${order.id}`}
                        className="font-medium text-brand-700 hover:underline">
                        {order.order_number}
                      </Link>
                      <p className="text-xs text-muted">{order.item_count} item(s)</p>
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <span>{order.customer_name}</span>
                        <RiskBadge level={order.customer_risk} />
                      </div>
                      <p className="text-xs text-muted">{order.customer_phone}</p>
                    </td>
                    <td className="px-4 py-2.5 text-muted">{order.shipping_district}</td>
                    <td className="px-4 py-2.5"><StatusBadge status={order.status} /></td>
                    <td className="px-4 py-2.5 text-right font-medium tabular-nums">
                      {money(order.cod_amount)}
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs text-muted">
                      {relative(order.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <ul className="space-y-2 lg:hidden">
            {orders.map((order) => (
              <li key={order.id}>
                <Link to={`/orders/${order.id}`} className="card block p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-medium text-brand-700">{order.order_number}</p>
                      <p className="truncate text-sm">{order.customer_name}</p>
                      <p className="text-xs text-muted">{order.customer_phone}</p>
                    </div>
                    <div className="shrink-0 text-right">
                      <StatusBadge status={order.status} />
                      <p className="mt-1 text-sm font-medium tabular-nums">
                        {money(order.cod_amount)}
                      </p>
                    </div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
