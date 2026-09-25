import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money } from "@/lib/format";
import { Alert, BigNumber, EmptyState, Figure, PageHeader, PageLoader } from "@/components/ui";

const TILE_TONES = [
  "bg-[linear-gradient(160deg,#EFE9DE_0%,#DCD2C0_100%)]",
  "bg-[linear-gradient(160deg,#EADBCB_0%,#CFB395_100%)]",
  "bg-[linear-gradient(160deg,#ECEAE2_0%,#D5D2C4_100%)]",
  "bg-[linear-gradient(160deg,#F4ECCB_0%,#E6D49A_100%)]",
];

export default function Products() {
  const { storeId } = useAuth();
  const [view, setView] = useState("grid");

  const { data, isLoading, error } = useQuery({
    queryKey: ["products", storeId],
    queryFn: async () => (await api.get("/products/")).data,
    enabled: Boolean(storeId),
  });

  const products = data?.results || [];

  if (isLoading) return <PageLoader label="Loading products" />;
  if (error) return <Alert>Could not load products.</Alert>;

  return (
    <div className="space-y-6">
      <PageHeader
        tone="white"
        eyebrow="Catalog"
        title="Products"
        note="What you sell, and how much is left"
        aside={<BigNumber value={data?.count ?? products.length} tone="text-ink/25"
          label="products in the catalog" />}
        actions={
          <div className="flex rounded-[3px] border border-line p-0.5 text-xs">
            {[["grid", "Gallery"], ["list", "List"]].map(([key, label]) => (
              <button key={key} type="button" onClick={() => setView(key)}
                className={`rounded-[2px] px-3 py-1.5 transition ${
                  view === key ? "bg-ink text-paper" : "text-muted hover:text-ink"
                }`}>
                {label}
              </button>
            ))}
          </div>
        }
      />

      {products.length === 0 ? (
        <EmptyState
          title="No products yet"
          description="Add what you sell so you can build orders quickly."
        />
      ) : view === "grid" ? (
        <div className="grid grid-cols-2 gap-x-4 gap-y-8 md:grid-cols-3 xl:grid-cols-4">
          {products.map((product, index) => (
            <ProductTile key={product.id} product={product} tone={TILE_TONES[index % TILE_TONES.length]} />
          ))}
        </div>
      ) : (
        <ProductTable products={products} />
      )}
    </div>
  );
}

function ProductTile({ product, tone }) {
  const available = product.total_stock?.available ?? 0;
  const low = available <= product.low_stock_threshold;
  return (
    <article className="group">
      <div className={`relative aspect-[4/5] overflow-hidden rounded-[3px] ${tone}`}>
        {product.primary_image ? (
          <img src={product.primary_image} alt={product.name}
            className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]" />
        ) : (
          <div className="flex h-full items-center justify-center">
            <span className="font-display text-8xl italic text-ink/15">
              {product.name.trim().charAt(0)}
            </span>
          </div>
        )}
        {low && (
          <span className="absolute left-3 top-3 rounded-[2px] bg-butter px-2 py-0.5 text-[11px] font-medium">
            {available === 0 ? "Sold out" : "Running low"}
          </span>
        )}
      </div>
      <div className="mt-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-[0.14em] text-muted">
            {product.category_name || product.sku || "Product"}
          </p>
          <h3 className="mt-0.5 truncate font-display text-xl leading-tight">{product.name}</h3>
        </div>
        <p className="shrink-0 font-display text-xl tabular-nums">
          <Figure value={money(product.selling_price)} />
        </p>
      </div>
      <p className={`mt-1 text-xs ${low ? "font-medium text-warn" : "text-muted"}`}>
        {available} in stock
      </p>
    </article>
  );
}

function ProductTable({ products }) {
  return (
    <div className="overflow-hidden rounded-[4px] border border-line bg-white">
      <table className="w-full text-sm">
        <thead className="table-head">
          <tr>
            <th className="px-5 py-3 font-medium">Product</th>
            <th className="px-5 py-3 font-medium">SKU</th>
            <th className="px-5 py-3 text-right font-medium">Price</th>
            <th className="px-5 py-3 text-right font-medium">Available</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {products.map((product) => {
            const available = product.total_stock?.available ?? 0;
            const low = available <= product.low_stock_threshold;
            return (
              <tr key={product.id} className="hover:bg-paper/60">
                <td className="px-5 py-3">
                  <p className="font-display text-lg leading-tight">{product.name}</p>
                  {product.category_name && (
                    <p className="text-xs text-muted">{product.category_name}</p>
                  )}
                </td>
                <td className="px-5 py-3 text-xs text-muted">{product.sku}</td>
                <td className="px-5 py-3 text-right tabular-nums">{money(product.selling_price)}</td>
                <td className={`px-5 py-3 text-right tabular-nums ${low ? "font-medium text-warn" : ""}`}>
                  {available}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
