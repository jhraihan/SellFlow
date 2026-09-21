import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money } from "@/lib/format";
import { Alert, EmptyState, PageLoader } from "@/components/ui";

export default function Products() {
  const { storeId } = useAuth();

  const { data, isLoading, error } = useQuery({
    queryKey: ["products", storeId],
    queryFn: async () => (await api.get("/products/")).data,
    enabled: Boolean(storeId),
  });

  const products = data?.results || [];

  if (isLoading) return <PageLoader label="Loading products" />;
  if (error) return <Alert>Could not load products.</Alert>;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Products</h1>
        <p className="text-sm text-muted">Your catalog and stock levels.</p>
      </div>

      {products.length === 0 ? (
        <EmptyState
          title="No products yet"
          description="Add what you sell so you can build orders quickly."
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-line bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-line bg-surface text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-2.5 font-medium">Product</th>
                <th className="px-4 py-2.5 font-medium">SKU</th>
                <th className="px-4 py-2.5 text-right font-medium">Price</th>
                <th className="px-4 py-2.5 text-right font-medium">Available</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {products.map((product) => {
                const available = product.total_stock?.available ?? 0;
                const low = available <= product.low_stock_threshold;
                return (
                  <tr key={product.id} className="hover:bg-surface">
                    <td className="px-4 py-2.5">
                      <p className="font-medium">{product.name}</p>
                      {product.category_name && (
                        <p className="text-xs text-muted">{product.category_name}</p>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-muted">{product.sku}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      {money(product.selling_price)}
                    </td>
                    <td
                      className={`px-4 py-2.5 text-right tabular-nums ${
                        low ? "font-medium text-warn" : ""
                      }`}
                    >
                      {available}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
