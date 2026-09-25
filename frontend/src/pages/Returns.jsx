import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money, relative } from "@/lib/format";
import { RotateCcw, Undo2 } from "lucide-react";
import {
  Alert, BigNumber, EmptyState, Field, Figure, Modal, PageHeader, PageLoader, Spinner,
} from "@/components/ui";

const REASONS = [
  ["customer_refused", "Customer refused delivery"],
  ["wrong_item", "Wrong item sent"],
  ["damaged", "Damaged in transit"],
  ["size_issue", "Size or fit issue"],
  ["not_available", "Customer not available"],
  ["quality", "Quality not as expected"],
  ["fake_order", "Fake order"],
  ["other", "Other"],
];

const STATUS_CLASSES = {
  initiated: "bg-butter-soft text-[#7A600E] border-butter-deep",
  received: "bg-[#E4ECF2] text-[#34506A] border-[#CAD8E4]",
  resolved: "bg-[#E4EEE2] text-ok border-[#C8DBC5]",
};

export default function Returns() {
  const { storeId, can } = useAuth();
  const queryClient = useQueryClient();
  const [openFor, setOpenFor] = useState(false);
  const [resolveFor, setResolveFor] = useState(null);
  const [failure, setFailure] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["returns", storeId],
    queryFn: async () => (await api.get("/returns/")).data,
    enabled: Boolean(storeId),
  });

  const { data: analytics } = useQuery({
    queryKey: ["return-analytics", storeId],
    queryFn: async () => (await api.get("/returns/analytics/")).data,
    enabled: Boolean(storeId) && can("view_analytics"),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["returns"] });
    queryClient.invalidateQueries({ queryKey: ["return-analytics"] });
    queryClient.invalidateQueries({ queryKey: ["orders"] });
  };

  const receive = useMutation({
    mutationFn: (id) => api.post(`/returns/${id}/receive/`, {}),
    onSuccess: refresh,
    onError: (err) => setFailure(errorMessage(err)),
  });

  const returns = data?.results || [];

  if (isLoading) return <PageLoader label="Loading returns" />;
  if (error) return <Alert>Could not load returns.</Alert>;

  return (
    <div className="space-y-5">
      <PageHeader
        icon={Undo2}
        tone="clay"
        eyebrow="Reverse logistics"
        title="Returns"
        note="What came back, and what it cost"
        aside={<BigNumber value={analytics?.total_returns ?? returns.length} tone="text-clay/60"
          labelTone="text-[#8A6446]" label="parcels came back" />}
        actions={can("record_returns") && (
          <button type="button" className="btn-dark"
            onClick={() => setOpenFor(true)}><RotateCcw className="h-4 w-4" /> Record a return</button>
        )}
      />

      {failure && <Alert onDismiss={() => setFailure("")}>{failure}</Alert>}

      {analytics && analytics.total_returns > 0 && (
        <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Returns" value={analytics.total_returns} />
          <Stat label="Return rate" value={`${analytics.return_rate}%`}
            tone={Number(analytics.return_rate) > 20 ? "danger" : undefined} />
          <Stat label="Total loss" value={money(analytics.total_loss)} tone="danger" />
          <Stat label="Written off" value={money(analytics.written_off_value)} />
        </section>
      )}

      {returns.length === 0 ? (
        <EmptyState title="No returns yet"
          description="Parcels that come back are recorded here with their real cost." />
      ) : (
        <div className="overflow-hidden rounded-2xl border border-line bg-white">
          <table className="w-full text-sm">
            <thead className="table-head">
              <tr>
                <th className="px-4 py-2.5 font-medium">Order</th>
                <th className="px-4 py-2.5 font-medium">Reason</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 text-right font-medium">Loss</th>
                <th className="px-4 py-2.5 text-right font-medium">Opened</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {returns.map((row) => (
                <tr key={row.id} className="hover:bg-surface">
                  <td className="px-4 py-2.5">
                    <Link to={`/orders/${row.order}`}
                      className="font-medium link">
                      {row.order_number}
                    </Link>
                    <p className="text-xs text-muted">{row.customer_name}</p>
                  </td>
                  <td className="px-4 py-2.5 text-muted">{row.reason_display}</td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs ${
                      STATUS_CLASSES[row.status]
                    }`}>
                      {row.status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-danger">
                    {money(row.total_loss)}
                  </td>
                  <td className="px-4 py-2.5 text-right text-xs text-muted">
                    {relative(row.created_at)}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    {can("record_returns") && row.status === "initiated" && (
                      <button type="button" className="text-sm link"
                        onClick={() => receive.mutate(row.id)}>Mark received</button>
                    )}
                    {can("record_returns") && row.status === "received" && (
                      <button type="button" className="text-sm link"
                        onClick={() => setResolveFor(row)}>Resolve</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {analytics?.by_reason?.length > 0 && (
        <section className="card p-4">
          <h2 className="mb-3 section-title">Why parcels come back</h2>
          <ul className="space-y-1.5 text-sm">
            {analytics.by_reason.map((row) => {
              const label = REASONS.find(([v]) => v === row.reason)?.[1] || row.reason;
              return (
                <li key={row.reason} className="flex justify-between">
                  <span className="text-muted">{label}</span>
                  <span className="tabular-nums">{row.count}</span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <OpenReturnModal open={openFor} onClose={() => setOpenFor(false)}
        onDone={() => { setOpenFor(false); refresh(); }} onError={setFailure} />

      <ResolveModal record={resolveFor} onClose={() => setResolveFor(null)}
        onDone={() => { setResolveFor(null); refresh(); }} onError={setFailure} />
    </div>
  );
}

function Stat({ label, value, tone }) {
  return (
    <div className="card p-5">
      <p className="eyebrow">{label}</p>
      <p className={`mt-5 text-3xl font-extrabold leading-none tracking-[-0.035em] tabular-nums ${
        tone === "danger" ? "text-danger" : ""
      }`}><Figure value={value} /></p>
    </div>
  );
}

function OpenReturnModal({ open, onClose, onDone, onError }) {
  const { storeId } = useAuth();
  const [orderId, setOrderId] = useState("");
  const [reason, setReason] = useState("customer_refused");
  const [note, setNote] = useState("");
  const [charge, setCharge] = useState("0");

  const { data: orders } = useQuery({
    queryKey: ["returnable-orders", storeId],
    queryFn: async () =>
      (await api.get("/orders/?status=shipped&status=out_for_delivery&status=delivered")).data,
    enabled: open && Boolean(storeId),
  });

  const create = useMutation({
    mutationFn: (body) => api.post("/returns/", body),
    onSuccess: onDone,
    onError: (err) => onError(errorMessage(err)),
  });

  if (!open) return null;

  return (
    <Modal open title="Record a return" onClose={onClose}
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="btn-primary" disabled={!orderId || create.isPending}
            onClick={() => create.mutate({
              order: Number(orderId), reason, reason_note: note, return_charge: charge,
            })}>
            {create.isPending && <Spinner className="h-4 w-4" />}
            Record return
          </button>
        </>
      }>
      <div className="space-y-4">
        <Field label="Order" required>
          <select className="input" value={orderId}
            onChange={(e) => setOrderId(e.target.value)}>
            <option value="">Choose an order...</option>
            {(orders?.results || []).map((order) => (
              <option key={order.id} value={order.id}>
                {order.order_number} - {order.customer_name} - {money(order.total_amount)}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Why did it come back?" required>
          <select className="input" value={reason}
            onChange={(e) => setReason(e.target.value)}>
            {REASONS.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </Field>

        <Field label="Return charge"
          hint="What the courier charged to bring it back.">
          <input className="input" inputMode="decimal" value={charge}
            onChange={(e) => setCharge(e.target.value)} />
        </Field>

        <Field label="Note">
          <input className="input" value={note} placeholder="Optional"
            onChange={(e) => setNote(e.target.value)} />
        </Field>
      </div>
    </Modal>
  );
}

function ResolveModal({ record, onClose, onDone, onError }) {
  const [refund, setRefund] = useState("0");
  const [note, setNote] = useState("");
  const [damaged, setDamaged] = useState({});

  const resolve = useMutation({
    mutationFn: (body) => api.post(`/returns/${record.id}/resolve/`, body),
    onSuccess: onDone,
    onError: (err) => onError(errorMessage(err)),
  });

  const { data: detail } = useQuery({
    queryKey: ["return-detail", record?.id],
    queryFn: async () => (await api.get(`/returns/${record.id}/`)).data,
    enabled: Boolean(record),
  });

  if (!record) return null;

  const items = detail?.items || [];

  return (
    <Modal open title={`Resolve return for ${record.order_number}`} onClose={onClose}
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="btn-primary" disabled={resolve.isPending}
            onClick={() => resolve.mutate({
              item_dispositions: items.map((item) => ({
                return_item: item.id,
                condition: damaged[item.id] ? "damaged" : "sellable",
                restock: !damaged[item.id],
              })),
              refund_amount: refund,
              resolution_note: note,
            })}>
            {resolve.isPending && <Spinner className="h-4 w-4" />}
            Resolve
          </button>
        </>
      }>
      <div className="space-y-4">
        <div>
          <p className="label">What condition are the items in?</p>
          <ul className="space-y-2">
            {items.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-3
                                           rounded-lg border border-line px-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm">{item.product_name}</p>
                  <p className="text-xs text-muted">Qty {item.quantity}</p>
                </div>
                <label className="flex shrink-0 items-center gap-2 text-sm">
                  <input type="checkbox" checked={Boolean(damaged[item.id])}
                    onChange={(e) =>
                      setDamaged({ ...damaged, [item.id]: e.target.checked })} />
                  Damaged
                </label>
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-muted">
            Sellable items go back into stock. Damaged ones are written off as a loss.
          </p>
        </div>

        <Field label="Refund to customer"
          hint="Only if they already paid something.">
          <input className="input" inputMode="decimal" value={refund}
            onChange={(e) => setRefund(e.target.value)} />
        </Field>

        <Field label="Note">
          <input className="input" value={note} placeholder="Optional"
            onChange={(e) => setNote(e.target.value)} />
        </Field>
      </div>
    </Modal>
  );
}
