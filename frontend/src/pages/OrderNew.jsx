import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, errorCode, errorMessage, fieldErrors } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money } from "@/lib/format";
import { Alert, Field, RiskBadge, Spinner } from "@/components/ui";

const DRAFT_KEY = "shopflow.order-draft";

function loadDraft() {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveDraft(draft) {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
  } catch {
    /* ignore */
  }
}

function clearDraft() {
  try {
    localStorage.removeItem(DRAFT_KEY);
  } catch {
    /* ignore */
  }
}

const EMPTY = {
  phone: "", name: "", district: "Dhaka", thana: "", address_line: "",
  note: "", discount: "0", advance: "0", source: "messenger",
};

export default function OrderNew() {
  const navigate = useNavigate();
  const { storeId } = useAuth();

  const [form, setForm] = useState(() => loadDraft()?.form || EMPTY);
  const [lines, setLines] = useState(() => loadDraft()?.lines || []);
  const [customer, setCustomer] = useState(null);
  const [lookupState, setLookupState] = useState("idle");
  const [failure, setFailure] = useState("");
  const [errors, setErrors] = useState({});
  const [duplicate, setDuplicate] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [picker, setPicker] = useState("");

  const productRef = useRef(null);

  const { data: products } = useQuery({
    queryKey: ["products-for-order", storeId],
    queryFn: async () => (await api.get("/products/?page_size=100")).data,
    enabled: Boolean(storeId),
  });

  const { data: settings } = useQuery({
    queryKey: ["store-settings", storeId],
    queryFn: async () => (await api.get(`/stores/${storeId}/settings/`)).data,
    enabled: Boolean(storeId),
  });

  useEffect(() => {
    saveDraft({ form, lines });
  }, [form, lines]);

  const deliveryCharge = useMemo(() => {
    if (!settings) return 0;
    const overrides = settings.district_charge_overrides || {};
    const district = (form.district || "").trim();
    if (overrides[district] !== undefined) return Number(overrides[district]);
    if (district.toLowerCase() === "dhaka") {
      return Number(settings.delivery_charge_inside_dhaka || 0);
    }
    return Number(settings.delivery_charge_outside_dhaka || 0);
  }, [settings, form.district]);

  const subtotal = lines.reduce(
    (sum, line) => sum + Number(line.unit_price) * line.quantity, 0,
  );
  const discount = Number(form.discount || 0);
  const advance = Number(form.advance || 0);

  const freeThreshold = settings?.free_delivery_threshold;
  const delivery =
    freeThreshold && subtotal - discount >= Number(freeThreshold)
      ? 0
      : deliveryCharge;

  const total = Math.max(subtotal - discount + delivery, 0);
  const cod = Math.max(total - advance, 0);

  async function lookupPhone(phone) {
    const cleaned = phone.replace(/\s/g, "");
    if (cleaned.length < 11) {
      setCustomer(null);
      setLookupState("idle");
      return;
    }
    setLookupState("loading");
    try {
      const { data } = await api.get(
        `/customers/lookup/?phone=${encodeURIComponent(cleaned)}`,
      );
      if (data.found) {
        setCustomer(data.customer);
        setLookupState("found");
        setForm((prev) => ({
          ...prev,
          name: prev.name || data.customer.name,
          district: data.customer.default_address?.district || prev.district,
          thana: data.customer.default_address?.thana || prev.thana,
          address_line:
            prev.address_line || data.customer.default_address?.address_line || "",
        }));
      } else {
        setCustomer(null);
        setLookupState("new");
      }
    } catch {
      setLookupState("idle");
    }
  }

  function addLine(productId) {
    const product = (products?.results || []).find(
      (p) => String(p.id) === String(productId),
    );
    if (!product) return;

    setLines((prev) => {
      const existing = prev.find((l) => l.product === product.id && !l.variant);
      if (existing) {
        return prev.map((l) =>
          l === existing ? { ...l, quantity: l.quantity + 1 } : l,
        );
      }
      return [...prev, {
        product: product.id,
        variant: null,
        name: product.name,
        unit_price: product.selling_price,
        quantity: 1,
        available: product.total_stock?.available ?? null,
      }];
    });
    setPicker("");
    productRef.current?.focus();
  }

  function updateQuantity(index, quantity) {
    setLines((prev) =>
      prev.map((line, i) =>
        i === index ? { ...line, quantity: Math.max(1, quantity) } : line,
      ),
    );
  }

  function removeLine(index) {
    setLines((prev) => prev.filter((_, i) => i !== index));
  }

  function validate() {
    const next = {};
    if (!form.phone.trim()) next.phone = "Enter the customer's phone number.";
    if (!form.name.trim()) next.name = "Enter the customer's name.";
    if (!form.district.trim()) next.district = "Enter the district.";
    if (!form.address_line.trim()) next.address_line = "Enter the address.";
    if (lines.length === 0) next.items = "Add at least one item.";
    if (discount > subtotal) next.discount = "The discount is larger than the order.";
    if (advance > total) next.advance = "The advance is larger than the total.";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function submit(acknowledgeDuplicate = false) {
    if (!validate()) return;
    setFailure("");
    setSubmitting(true);

    const payload = {
      items: lines.map((l) => ({
        product: l.product, variant: l.variant, quantity: l.quantity,
      })),
      shipping: {
        recipient_name: form.name,
        recipient_phone: form.phone,
        district: form.district,
        thana: form.thana,
        address_line: form.address_line,
      },
      source: form.source,
      discount_amount: form.discount || "0",
      advance_paid: form.advance || "0",
      customer_note: form.note,
      acknowledge_duplicate: acknowledgeDuplicate,
    };

    if (customer) payload.customer = customer.id;
    else payload.new_customer = { name: form.name, phone: form.phone };

    try {
      const { data } = await api.post("/orders/", payload);
      clearDraft();
      navigate(`/orders/${data.id}`);
    } catch (error) {
      if (errorCode(error) === "POSSIBLE_DUPLICATE") {
        setDuplicate(error.response.data.error.details.orders || []);
      } else {
        const fields = fieldErrors(error);
        if (Object.keys(fields).length) setErrors(fields);
        setFailure(errorMessage(error));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5 pb-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">New order</h1>
          <p className="text-sm text-muted">Your typing is saved as you go.</p>
        </div>
        <button type="button" className="btn-secondary text-sm"
          onClick={() => { clearDraft(); setForm(EMPTY); setLines([]); setCustomer(null); }}>
          Clear
        </button>
      </div>

      {failure && <Alert onDismiss={() => setFailure("")}>{failure}</Alert>}

      {customer?.is_blacklisted && (
        <Alert tone="danger" title="This customer is blacklisted">
          {customer.blacklist_reason || "No reason recorded."}
        </Alert>
      )}

      {customer && !customer.is_blacklisted && customer.returned_count > 0 && (
        <Alert tone="warn" title="Check before shipping">
          {customer.returned_count} of this customer's {customer.total_orders} orders
          came back ({customer.return_rate}% return rate).
        </Alert>
      )}

      <section className="card space-y-4 p-4">
        <h2 className="text-sm font-semibold">Customer</h2>

        <Field label="Phone" required error={errors.phone}
          hint={
            lookupState === "loading" ? "Looking up..."
              : lookupState === "found" ? "Existing customer, details filled in."
              : lookupState === "new" ? "New customer."
              : "Type the full number to autofill."
          }>
          <div className="flex items-center gap-2">
            <input className="input" inputMode="numeric" autoFocus
              placeholder="01712345678" value={form.phone}
              onChange={(e) => {
                setForm({ ...form, phone: e.target.value });
                lookupPhone(e.target.value);
              }} />
            {lookupState === "loading" && <Spinner className="h-4 w-4 text-muted" />}
            {customer && <RiskBadge level={customer.risk_level} />}
          </div>
        </Field>

        <Field label="Name" required error={errors.name}>
          <input className="input" value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="District" required error={errors.district}>
            <input className="input" value={form.district}
              onChange={(e) => setForm({ ...form, district: e.target.value })} />
          </Field>
          <Field label="Thana / Area">
            <input className="input" value={form.thana}
              onChange={(e) => setForm({ ...form, thana: e.target.value })} />
          </Field>
        </div>

        <Field label="Address" required error={errors.address_line}>
          <textarea className="input" rows={2} value={form.address_line}
            onChange={(e) => setForm({ ...form, address_line: e.target.value })} />
        </Field>
      </section>

      <section className="card space-y-3 p-4">
        <h2 className="text-sm font-semibold">Items</h2>

        <Field error={errors.items}>
          <select ref={productRef} className="input" value={picker}
            onChange={(e) => addLine(e.target.value)} aria-label="Add a product">
            <option value="">Add a product...</option>
            {(products?.results || []).map((product) => (
              <option key={product.id} value={product.id}>
                {product.name} - {money(product.selling_price)}
                {product.total_stock ? ` (${product.total_stock.available} left)` : ""}
              </option>
            ))}
          </select>
        </Field>

        {lines.length > 0 && (
          <ul className="divide-y divide-line">
            {lines.map((line, index) => {
              const short = line.available !== null && line.quantity > line.available;
              return (
                <li key={`${line.product}-${index}`} className="flex items-center gap-3 py-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">{line.name}</p>
                    <p className="text-xs text-muted">
                      {money(line.unit_price)} each
                      {short && (
                        <span className="ml-2 text-danger">
                          only {line.available} in stock
                        </span>
                      )}
                    </p>
                  </div>
                  <input type="number" min={1} value={line.quantity}
                    onChange={(e) => updateQuantity(index, Number(e.target.value))}
                    className="input w-16 text-center" aria-label="Quantity" />
                  <span className="w-24 text-right text-sm font-medium tabular-nums">
                    {money(Number(line.unit_price) * line.quantity)}
                  </span>
                  <button type="button" onClick={() => removeLine(index)}
                    className="text-muted hover:text-danger" aria-label="Remove">&times;</button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="card space-y-4 p-4">
        <h2 className="text-sm font-semibold">Payment</h2>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Discount" error={errors.discount}>
            <input className="input" inputMode="decimal" value={form.discount}
              onChange={(e) => setForm({ ...form, discount: e.target.value })} />
          </Field>
          <Field label="Advance paid" error={errors.advance}>
            <input className="input" inputMode="decimal" value={form.advance}
              onChange={(e) => setForm({ ...form, advance: e.target.value })} />
          </Field>
        </div>

        <Field label="Where did this order come from?">
          <select className="input" value={form.source}
            onChange={(e) => setForm({ ...form, source: e.target.value })}>
            <option value="messenger">Facebook Messenger</option>
            <option value="instagram">Instagram</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="phone">Phone call</option>
            <option value="comment">Facebook comment</option>
            <option value="manual">Manual entry</option>
          </select>
        </Field>

        <Field label="Note for the customer">
          <input className="input" value={form.note}
            onChange={(e) => setForm({ ...form, note: e.target.value })} />
        </Field>

        <dl className="space-y-1 border-t border-line pt-3 text-sm">
          <Row label="Subtotal" value={money(subtotal)} />
          {discount > 0 && <Row label="Discount" value={`- ${money(discount)}`} />}
          <Row label="Delivery" value={money(delivery)} />
          <Row label="Total" value={money(total)} />
          {advance > 0 && <Row label="Advance paid" value={`- ${money(advance)}`} />}
          <div className="flex items-baseline justify-between border-t border-line pt-2">
            <dt className="font-semibold">Cash on delivery</dt>
            <dd className="text-xl font-semibold tabular-nums">{money(cod)}</dd>
          </div>
        </dl>
      </section>

      <div className="sticky bottom-16 z-20 -mx-4 border-t border-line bg-surface/95 px-4 py-3 backdrop-blur lg:bottom-0 lg:mx-0 lg:rounded-xl lg:border lg:px-3">
        <button type="button" onClick={() => submit(false)}
          disabled={submitting || lines.length === 0}
          className="btn-primary w-full py-3 text-base shadow-lg">
          {submitting && <Spinner className="h-4 w-4" />}
          Create order &middot; {money(cod)} COD
        </button>
      </div>

      {duplicate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setDuplicate(null)} />
          <div className="relative z-10 w-full max-w-md rounded-xl bg-white p-5 shadow-xl">
            <h2 className="text-sm font-semibold">This might be a duplicate</h2>
            <p className="mt-1 text-sm text-muted">
              This customer already has a recent open order with one of these products.
            </p>
            <ul className="mt-3 space-y-1 text-sm">
              {duplicate.map((order) => (
                <li key={order.id} className="flex justify-between">
                  <span className="font-medium">{order.order_number}</span>
                  <span className="text-muted">{order.status}</span>
                </li>
              ))}
            </ul>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="btn-secondary"
                onClick={() => setDuplicate(null)}>Cancel</button>
              <button type="button" className="btn-primary"
                onClick={() => { setDuplicate(null); submit(true); }}>
                Create anyway
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-baseline justify-between">
      <dt className="text-muted">{label}</dt>
      <dd className="tabular-nums">{value}</dd>
    </div>
  );
}
