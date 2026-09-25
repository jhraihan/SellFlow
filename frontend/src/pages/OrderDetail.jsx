import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, downloadFile, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime, money, ORDER_STATUS_LABELS } from "@/lib/format";
import { Download, Receipt } from "lucide-react";
import { Alert, Figure, Modal, PageHeader, PageLoader, RiskBadge, Spinner, StatusBadge } from "@/components/ui";

const CANCEL_REASONS = [
  ["customer_cancelled", "Customer cancelled"],
  ["fake_order", "Fake or prank order"],
  ["unreachable", "Customer unreachable"],
  ["out_of_stock", "Out of stock"],
  ["duplicate", "Duplicate order"],
  ["price_dispute", "Price disagreement"],
  ["other", "Other"],
];

const CALL_OUTCOMES = [
  ["confirmed", "Confirmed"],
  ["no_answer", "No answer"],
  ["call_later", "Asked to call later"],
  ["cancelled", "Cancelled"],
  ["fake", "Fake order"],
];

export default function OrderDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const [failure, setFailure] = useState("");
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState("customer_cancelled");
  const [callOpen, setCallOpen] = useState(false);
  const [outcome, setOutcome] = useState("confirmed");

  const { data: order, isLoading, error } = useQuery({
    queryKey: ["order", id],
    queryFn: async () => (await api.get(`/orders/${id}/`)).data,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["order", id] });
    queryClient.invalidateQueries({ queryKey: ["orders"] });
    queryClient.invalidateQueries({ queryKey: ["order-stats"] });
  };

  const changeStatus = useMutation({
    mutationFn: (body) => api.patch(`/orders/${id}/status/`, body),
    onSuccess: () => { setFailure(""); setCancelOpen(false); refresh(); },
    onError: (err) => setFailure(errorMessage(err)),
  });

  const logCall = useMutation({
    mutationFn: (body) => api.post(`/orders/${id}/confirm/`, body),
    onSuccess: () => { setFailure(""); setCallOpen(false); refresh(); },
    onError: (err) => setFailure(errorMessage(err)),
  });

  if (isLoading) return <PageLoader label="Loading order" />;
  if (error) return <Alert>Could not load this order.</Alert>;

  const canAct = can("confirm_orders");
  const transitions = (order.allowed_transitions || []).filter(
    (s) => s !== "cancelled",
  );

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <Link to="/orders" className="eyebrow inline-block hover:text-ink">&larr; All orders</Link>
      <PageHeader
        icon={Receipt}
        tone="white"
        eyebrow={order.source ? `Order from ${order.source.replace(/_/g, " ")}` : "Order"}
        title={order.order_number}
        note={`Placed ${dateTime(order.created_at)}`}
        aside={<StatusBadge status={order.status} />}
        actions={
        <>
          <button type="button" className="btn-secondary text-sm"
            onClick={() => downloadFile(`/orders/${id}/invoice/`,
              `invoice-${order.order_number}.pdf`).catch(
              (err) => setFailure(errorMessage(err, "Could not download the invoice.")))}>
            <Download className="h-4 w-4" /> Invoice
          </button>
          <button type="button" className="btn-secondary text-sm"
            onClick={() => downloadFile(`/orders/${id}/label/`,
              `label-${order.order_number}.pdf`).catch(
              (err) => setFailure(errorMessage(err, "Could not download the label.")))}>
            <Download className="h-4 w-4" /> Label
          </button>
        </>
        }
      >
      {canAct && (
        <div className="flex flex-wrap gap-2 border-t border-line pt-5">
          {order.status === "pending" && (
            <button type="button" className="btn-primary"
              onClick={() => setCallOpen(true)}>Log call / Confirm</button>
          )}
          {transitions.map((status) => (
            <button key={status} type="button" className="btn-secondary"
              disabled={changeStatus.isPending}
              onClick={() => changeStatus.mutate({ status })}>
              Mark {ORDER_STATUS_LABELS[status] || status}
            </button>
          ))}
          {order.allowed_transitions?.includes("cancelled") && (
            <button type="button" className="btn-secondary text-danger"
              onClick={() => setCancelOpen(true)}>Cancel</button>
          )}
        </div>
      )}
      </PageHeader>

      {failure && <Alert onDismiss={() => setFailure("")}>{failure}</Alert>}

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="card p-6 lg:col-span-2">
          <p className="eyebrow">In the parcel</p>
          <h2 className="mb-3 mt-1 section-title">Items</h2>
          <ul className="divide-y divide-line text-sm">
            {order.items.map((item) => (
              <li key={item.id} className="flex items-start justify-between gap-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-[15px] font-semibold leading-snug">{item.product_name}</p>
                  {item.variant_label && (
                    <p className="text-xs text-muted">{item.variant_label}</p>
                  )}
                  <p className="text-xs text-muted">
                    {money(item.unit_price)} &times; {item.quantity}
                  </p>
                </div>
                <span className="shrink-0 font-medium tabular-nums">
                  {money(item.line_total)}
                </span>
              </li>
            ))}
          </ul>

          <dl className="mt-3 space-y-1.5 border-t border-line pt-4 text-sm">
            <Row label="Subtotal" value={money(order.subtotal)} />
            {Number(order.discount_amount) > 0 && (
              <Row label="Discount" value={`- ${money(order.discount_amount)}`} />
            )}
            <Row label="Delivery" value={money(order.delivery_charge)} />
            <Row label="Total" value={money(order.total_amount)} />
            {Number(order.advance_paid) > 0 && (
              <Row label="Advance paid" value={`- ${money(order.advance_paid)}`} />
            )}
            <div className="mt-2 flex items-baseline justify-between rounded-lg bg-butter px-4 py-3">
              <dt className="text-base font-bold">Cash on delivery</dt>
              <dd className="text-3xl font-extrabold tracking-[-0.035em] tabular-nums">
                <Figure value={money(order.cod_amount)} />
              </dd>
            </div>
          </dl>
        </section>

        <div className="space-y-4">
          <section className="rounded-2xl bg-sand p-5">
            <p className="eyebrow text-olive/70">Deliver to</p>
            <h2 className="mb-2 mt-1 section-title">Customer</h2>
            <div className="flex items-center gap-2">
              <Link to={`/customers/${order.customer}`}
                className="text-sm font-medium link">
                {order.customer_name}
              </Link>
              <RiskBadge level={order.customer_risk} />
            </div>
            <p className="text-sm text-muted">{order.customer_phone}</p>
            <p className="mt-2 text-sm">
              {order.shipping_address}
              {order.shipping_thana && `, ${order.shipping_thana}`}
              {order.shipping_district && `, ${order.shipping_district}`}
            </p>
            {order.customer_note && (
              <p className="mt-3 rounded-lg bg-white/70 p-2.5 text-xs">
                <span className="font-medium">Note: </span>{order.customer_note}
              </p>
            )}
          </section>

          <section className="card p-5">
            <p className="eyebrow">History</p>
            <h2 className="mb-4 mt-1 section-title">Timeline</h2>
            <ol className="relative space-y-4 border-l border-line pl-5 text-sm">
              {(order.status_history || []).map((row) => (
                <li key={row.id} className="relative">
                  <span className="absolute -left-[1.6rem] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-olive" />
                  <p className="text-[15px] font-semibold leading-snug">{row.to_status_display}</p>
                  <p className="text-xs text-muted">
                    {dateTime(row.created_at)}
                    {row.actor_name && ` by ${row.actor_name}`}
                  </p>
                  {row.note && <p className="text-xs text-muted">{row.note}</p>}
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>

      <Modal open={callOpen} title="Log the confirmation call"
        onClose={() => setCallOpen(false)}
        footer={
          <>
            <button type="button" className="btn-secondary"
              onClick={() => setCallOpen(false)}>Cancel</button>
            <button type="button" className="btn-primary"
              disabled={logCall.isPending}
              onClick={() => logCall.mutate({ outcome })}>
              {logCall.isPending && <Spinner className="h-4 w-4" />}
              Save
            </button>
          </>
        }>
        <label className="label">What happened?</label>
        <select className="input" value={outcome}
          onChange={(e) => setOutcome(e.target.value)}>
          {CALL_OUTCOMES.map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
        <p className="mt-2 text-xs text-muted">
          Attempts so far: {order.confirmation_attempts}
        </p>
      </Modal>

      <Modal open={cancelOpen} title="Cancel this order"
        onClose={() => setCancelOpen(false)}
        footer={
          <>
            <button type="button" className="btn-secondary"
              onClick={() => setCancelOpen(false)}>Keep order</button>
            <button type="button" className="btn-danger"
              disabled={changeStatus.isPending}
              onClick={() => changeStatus.mutate({
                status: "cancelled", reason: cancelReason,
              })}>
              {changeStatus.isPending && <Spinner className="h-4 w-4" />}
              Cancel order
            </button>
          </>
        }>
        <label className="label">Why?</label>
        <select className="input" value={cancelReason}
          onChange={(e) => setCancelReason(e.target.value)}>
          {CANCEL_REASONS.map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </Modal>
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
