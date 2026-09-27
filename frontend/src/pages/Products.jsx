import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Package, PackagePlus, Pencil, Plus, SlidersHorizontal } from "lucide-react";
import { api, errorMessage, fieldErrors } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money } from "@/lib/format";
import {
  Alert, BigNumber, EmptyState, Field, Figure, Modal, PageHeader, PageLoader, Spinner,
} from "@/components/ui";

const TILE_TONES = [
  "bg-[linear-gradient(160deg,#EFE9DE_0%,#DCD2C0_100%)]",
  "bg-[linear-gradient(160deg,#EADBCB_0%,#CFB395_100%)]",
  "bg-[linear-gradient(160deg,#ECEAE2_0%,#D5D2C4_100%)]",
  "bg-[linear-gradient(160deg,#F4ECCB_0%,#E6D49A_100%)]",
];

export default function Products() {
  const { storeId, can } = useAuth();
  const [view, setView] = useState("grid");
  const [editing, setEditing] = useState(null);
  const [stockFor, setStockFor] = useState(null);
  const [notice, setNotice] = useState("");
  const [failure, setFailure] = useState("");
  const manage = can("manage_products");

  const { data, isLoading, error } = useQuery({
    queryKey: ["products", storeId],
    queryFn: async () => (await api.get("/products/?page_size=100")).data,
    enabled: Boolean(storeId),
  });

  const products = data?.results || [];

  if (isLoading) return <PageLoader label="Loading products" />;
  if (error) return <Alert>Could not load products.</Alert>;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Package}
        tone="white"
        eyebrow="Catalog"
        title="Products"
        note="What you sell, and how much is left"
        aside={<BigNumber value={data?.count ?? products.length} tone="text-ink/25"
          label="products in the catalog" />}
        actions={
          <>
            <div className="flex rounded-lg border border-line p-0.5 text-xs">
              {[["grid", "Gallery"], ["list", "List"]].map(([key, label]) => (
                <button key={key} type="button" onClick={() => setView(key)}
                  className={`rounded-md px-3 py-1.5 font-semibold transition ${
                    view === key ? "bg-ink text-paper" : "text-muted hover:text-ink"
                  }`}>
                  {label}
                </button>
              ))}
            </div>
            {manage && (
              <button type="button" className="btn-primary" onClick={() => setEditing({})}>
                <Plus className="h-4 w-4" strokeWidth={2.5} /> Add product
              </button>
            )}
          </>
        }
      />

      {notice && <Alert tone="ok" onDismiss={() => setNotice("")}>{notice}</Alert>}
      {failure && <Alert onDismiss={() => setFailure("")}>{failure}</Alert>}

      {products.length === 0 ? (
        <EmptyState
          icon={PackagePlus}
          title="No products yet"
          description="Add what you sell so you can build orders quickly."
          action={manage
            ? <button type="button" className="btn-primary" onClick={() => setEditing({})}>
                <Plus className="h-4 w-4" strokeWidth={2.5} /> Add your first product
              </button>
            : undefined}
        />
      ) : view === "grid" ? (
        <div className="grid grid-cols-2 gap-x-4 gap-y-8 md:grid-cols-3 xl:grid-cols-4">
          {products.map((product, index) => (
            <ProductTile key={product.id} product={product} manage={manage}
              tone={TILE_TONES[index % TILE_TONES.length]}
              onEdit={() => setEditing(product)} onStock={() => setStockFor(product)} />
          ))}
        </div>
      ) : (
        <ProductTable products={products} manage={manage}
          onEdit={setEditing} onStock={setStockFor} />
      )}

      <ProductModal product={editing} onClose={() => setEditing(null)}
        onSaved={(name, created) => {
          setEditing(null);
          setNotice(created ? `${name} added to your catalog.` : `${name} updated.`);
        }}
        onError={setFailure} />

      <StockModal product={stockFor} onClose={() => setStockFor(null)}
        onSaved={setNotice} onError={setFailure} />
    </div>
  );
}

function ProductTile({ product, tone, manage, onEdit, onStock }) {
  const available = product.total_stock?.available ?? 0;
  const low = available <= product.low_stock_threshold;
  return (
    <article className="group">
      <div className={`relative aspect-[4/5] overflow-hidden rounded-lg ${tone}`}>
        {product.primary_image ? (
          <img src={product.primary_image} alt={product.name}
            className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]" />
        ) : (
          <div className="flex h-full items-center justify-center">
            <span className="text-7xl font-extrabold tracking-[-0.05em] text-ink/10">
              {product.name.trim().charAt(0)}
            </span>
          </div>
        )}
        {low && (
          <span className="absolute left-3 top-3 rounded-md bg-butter px-2 py-0.5 text-[11px] font-semibold">
            {available === 0 ? "Sold out" : "Running low"}
          </span>
        )}
        {manage && (
          <div className="absolute inset-x-3 bottom-3 flex gap-2 opacity-0 transition group-hover:opacity-100">
            <button type="button" onClick={onStock}
              className="flex-1 rounded-lg bg-ink/85 px-2 py-1.5 text-xs font-semibold text-paper backdrop-blur hover:bg-ink">
              Stock
            </button>
            <button type="button" onClick={onEdit}
              className="flex-1 rounded-lg bg-white/90 px-2 py-1.5 text-xs font-semibold text-ink backdrop-blur hover:bg-white">
              Edit
            </button>
          </div>
        )}
      </div>
      <div className="mt-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-[0.14em] text-muted">
            {product.category_name || product.sku || "Product"}
          </p>
          <h3 className="mt-0.5 truncate text-base font-bold leading-snug tracking-tight">{product.name}</h3>
        </div>
        <p className="shrink-0 text-base font-extrabold tabular-nums">
          <Figure value={money(product.selling_price)} />
        </p>
      </div>
      <p className={`mt-1 text-xs ${low ? "font-semibold text-warn" : "text-muted"}`}>
        {available} in stock
      </p>
    </article>
  );
}

function ProductTable({ products, manage, onEdit, onStock }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-white shadow-soft">
      <table className="w-full text-sm">
        <thead className="table-head">
          <tr>
            <th className="px-5 py-3">Product</th>
            <th className="px-5 py-3">SKU</th>
            <th className="px-5 py-3 text-right">Price</th>
            <th className="px-5 py-3 text-right">Available</th>
            {manage && <th className="px-5 py-3" />}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {products.map((product) => {
            const available = product.total_stock?.available ?? 0;
            const low = available <= product.low_stock_threshold;
            return (
              <tr key={product.id} className="hover:bg-paper/60">
                <td className="px-5 py-3">
                  <p className="text-[15px] font-semibold leading-snug">{product.name}</p>
                  {product.category_name && (
                    <p className="text-xs text-muted">{product.category_name}</p>
                  )}
                </td>
                <td className="px-5 py-3 text-xs text-muted">{product.sku}</td>
                <td className="px-5 py-3 text-right tabular-nums">{money(product.selling_price)}</td>
                <td className={`px-5 py-3 text-right tabular-nums ${low ? "font-semibold text-warn" : ""}`}>
                  {available}
                </td>
                {manage && (
                  <td className="px-5 py-3">
                    <div className="flex justify-end gap-1.5">
                      <button type="button" onClick={() => onStock(product)}
                        className="rounded-lg border border-line p-1.5 text-muted transition hover:border-ink/30 hover:text-ink"
                        aria-label={`Stock for ${product.name}`}>
                        <SlidersHorizontal className="h-4 w-4" />
                      </button>
                      <button type="button" onClick={() => onEdit(product)}
                        className="rounded-lg border border-line p-1.5 text-muted transition hover:border-ink/30 hover:text-ink"
                        aria-label={`Edit ${product.name}`}>
                        <Pencil className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ProductModal({ product, onClose, onSaved, onError }) {
  const { storeId } = useAuth();
  const queryClient = useQueryClient();
  const editing = Boolean(product?.id);

  const { data: categories } = useQuery({
    queryKey: ["categories", storeId],
    queryFn: async () => (await api.get("/categories/")).data,
    enabled: Boolean(storeId) && Boolean(product),
  });

  const { register, handleSubmit, reset, setError,
    formState: { errors, isSubmitting } } = useForm();

  const defaults = {
    name: product?.name || "",
    sku: product?.sku || "",
    category: product?.category || "",
    selling_price: product?.selling_price || "",
    cost_price: product?.cost_price || "",
    low_stock_threshold: product?.low_stock_threshold ?? 5,
    weight_grams: product?.weight_grams ?? 500,
    opening_stock: "",
    description: product?.description || "",
  };

  async function onSubmit(values) {
    const payload = {
      name: values.name,
      sku: values.sku || "",
      category: values.category ? Number(values.category) : null,
      description: values.description || "",
      selling_price: values.selling_price,
      cost_price: values.cost_price || "0",
      low_stock_threshold: Number(values.low_stock_threshold || 0),
      weight_grams: Number(values.weight_grams || 0),
    };
    if (!editing && values.opening_stock !== "") {
      payload.opening_stock = Number(values.opening_stock);
    }

    try {
      if (editing) await api.patch(`/products/${product.id}/`, payload);
      else await api.post("/products/", payload);
      queryClient.invalidateQueries({ queryKey: ["products"] });
      queryClient.invalidateQueries({ queryKey: ["products-for-order"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      onSaved(values.name, !editing);
    } catch (error) {
      const fields = fieldErrors(error);
      for (const [key, message] of Object.entries(fields)) setError(key, { message });
      if (!Object.keys(fields).length) onError(errorMessage(error));
    }
  }

  return (
    <Modal open={Boolean(product)} onClose={onClose}
      title={editing ? "Edit product" : "Add a product"}
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" form="product-form" className="btn-primary" disabled={isSubmitting}>
            {isSubmitting && <Spinner className="h-4 w-4" />}
            {editing ? "Save changes" : "Add product"}
          </button>
        </>
      }>
      <form id="product-form" className="space-y-4" noValidate
        onSubmit={handleSubmit(onSubmit)}
        key={product?.id || "new"}>
        <Field label="Product name" required error={errors.name?.message}>
          <input className="input" autoFocus defaultValue={defaults.name}
            placeholder="Cotton kurti"
            {...register("name", { required: "Give the product a name." })} />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Selling price" required error={errors.selling_price?.message}>
            <input className="input" type="number" step="0.01" min="0" inputMode="decimal"
              defaultValue={defaults.selling_price} placeholder="1200"
              {...register("selling_price", { required: "What do you sell it for?" })} />
          </Field>
          <Field label="Cost price" error={errors.cost_price?.message}
            hint="What you paid. Used for profit.">
            <input className="input" type="number" step="0.01" min="0" inputMode="decimal"
              defaultValue={defaults.cost_price} placeholder="700"
              {...register("cost_price")} />
          </Field>
        </div>

        {!editing && (
          <Field label="Stock in hand" error={errors.opening_stock?.message}
            hint="How many you have right now. You can add more later.">
            <input className="input" type="number" min="0" inputMode="numeric"
              defaultValue={defaults.opening_stock} placeholder="10"
              {...register("opening_stock")} />
          </Field>
        )}

        <div className="grid grid-cols-2 gap-3">
          <Field label="SKU" error={errors.sku?.message} hint="Leave empty to generate one.">
            <input className="input" defaultValue={defaults.sku} placeholder="KURTI-0001"
              {...register("sku")} />
          </Field>
          <Field label="Category" error={errors.category?.message}>
            <select className="input" defaultValue={defaults.category} {...register("category")}>
              <option value="">No category</option>
              {(categories?.results || []).map((category) => (
                <option key={category.id} value={category.id}>{category.name}</option>
              ))}
            </select>
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Alert me below" error={errors.low_stock_threshold?.message}>
            <input className="input" type="number" min="0" inputMode="numeric"
              defaultValue={defaults.low_stock_threshold}
              {...register("low_stock_threshold")} />
          </Field>
          <Field label="Weight (grams)" error={errors.weight_grams?.message}
            hint="Couriers charge by weight.">
            <input className="input" type="number" min="0" inputMode="numeric"
              defaultValue={defaults.weight_grams}
              {...register("weight_grams")} />
          </Field>
        </div>

        <Field label="Description" error={errors.description?.message}>
          <textarea className="input" rows={2} defaultValue={defaults.description}
            placeholder="Colour, fabric, size..." {...register("description")} />
        </Field>

        {errors.root?.message && <Alert>{errors.root.message}</Alert>}
        <button type="button" className="hidden" onClick={() => reset()} />
      </form>
    </Modal>
  );
}

function StockModal({ product, onClose, onSaved, onError }) {
  const { storeId } = useAuth();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState("receive");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");

  const { data: stock } = useQuery({
    queryKey: ["stock", storeId, product?.id],
    queryFn: async () => (await api.get(`/stock/?product=${product.id}`)).data,
    enabled: Boolean(storeId) && Boolean(product?.id),
  });

  const items = (stock?.results || []).filter((item) => item.product_id === product?.id);
  const item = items[0];

  const save = useMutation({
    mutationFn: async () => {
      if (mode === "receive") {
        return api.post("/stock/receive/", {
          stock_item: item.id,
          quantity: Number(quantity),
          reason: reason || "Stock received",
        });
      }
      return api.post("/stock/adjust/", {
        stock_item: item.id,
        new_on_hand: Number(quantity),
        reason: reason || "Counted in the shop",
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      queryClient.invalidateQueries({ queryKey: ["stock"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      onSaved(mode === "receive"
        ? `Added ${quantity} to ${product.name}.`
        : `${product.name} now counted at ${quantity}.`);
      close();
    },
    onError: (error) => onError(errorMessage(error)),
  });

  function close() {
    setQuantity("");
    setReason("");
    setMode("receive");
    onClose();
  }

  return (
    <Modal open={Boolean(product)} onClose={close} title={`Stock: ${product?.name || ""}`}
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={close}>Cancel</button>
          <button type="button" className="btn-primary"
            disabled={save.isPending || !item || quantity === ""}
            onClick={() => save.mutate()}>
            {save.isPending && <Spinner className="h-4 w-4" />}
            {mode === "receive" ? "Add stock" : "Set count"}
          </button>
        </>
      }>
      {!item ? (
        <p className="text-sm text-muted">Loading stock...</p>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between rounded-xl bg-paper px-4 py-3">
            <span className="text-sm font-semibold text-ink/70">In hand now</span>
            <span className="text-2xl font-extrabold tabular-nums">{item.on_hand}</span>
          </div>

          <div className="flex gap-2">
            {[["receive", "Received new stock"], ["adjust", "Correct the count"]].map(([key, label]) => (
              <button key={key} type="button" onClick={() => setMode(key)}
                className={mode === key ? "pill-on" : "pill-off"}>
                {label}
              </button>
            ))}
          </div>

          <Field label={mode === "receive" ? "How many arrived?" : "Actual count in the shop"} required>
            <input className="input" type="number" min={mode === "receive" ? 1 : 0}
              inputMode="numeric" autoFocus value={quantity}
              onChange={(e) => setQuantity(e.target.value)} />
          </Field>

          <Field label="Reason" hint={mode === "adjust" ? "Required. What happened?" : "Optional."}>
            <input className="input" value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder={mode === "receive" ? "New delivery from supplier" : "Counted in the shop"} />
          </Field>

          {mode === "receive" && quantity !== "" && (
            <p className="text-sm text-muted">
              New total: <span className="font-bold text-ink">{item.on_hand + Number(quantity || 0)}</span>
            </p>
          )}
        </div>
      )}
    </Modal>
  );
}
