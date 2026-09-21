import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money, relative } from "@/lib/format";
import { Alert, EmptyState, PageLoader, RiskBadge } from "@/components/ui";

export default function Customers() {
  const { storeId } = useAuth();

  const { data, isLoading, error } = useQuery({
    queryKey: ["customers", storeId],
    queryFn: async () => (await api.get("/customers/")).data,
    enabled: Boolean(storeId),
  });

  const customers = data?.results || [];

  if (isLoading) return <PageLoader label="Loading customers" />;
  if (error) return <Alert>Could not load customers.</Alert>;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Customers</h1>
        <p className="text-sm text-muted">Who buys, and who sends parcels back.</p>
      </div>

      {customers.length === 0 ? (
        <EmptyState
          title="No customers yet"
          description="They are added automatically when you take an order."
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-line bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-line bg-surface text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-2.5 font-medium">Customer</th>
                <th className="px-4 py-2.5 font-medium">Risk</th>
                <th className="px-4 py-2.5 text-right font-medium">Orders</th>
                <th className="px-4 py-2.5 text-right font-medium">Returns</th>
                <th className="px-4 py-2.5 text-right font-medium">Lifetime</th>
                <th className="px-4 py-2.5 text-right font-medium">Last order</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {customers.map((customer) => (
                <tr key={customer.id} className="hover:bg-surface">
                  <td className="px-4 py-2.5">
                    <p className="font-medium">{customer.name}</p>
                    <p className="text-xs text-muted">{customer.phone}</p>
                  </td>
                  <td className="px-4 py-2.5">
                    <RiskBadge level={customer.risk_level} />
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums">
                    {customer.total_orders}
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums">
                    {customer.returned_count}
                    {Number(customer.return_rate) > 0 && (
                      <span className="ml-1 text-xs text-muted">
                        ({customer.return_rate}%)
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums">
                    {money(customer.lifetime_value)}
                  </td>
                  <td className="px-4 py-2.5 text-right text-xs text-muted">
                    {customer.last_order_at ? relative(customer.last_order_at) : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
