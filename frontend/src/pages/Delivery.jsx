import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime, money, relative } from "@/lib/format";
import {
  Alert, EmptyState, Field, Modal, PageLoader, Spinner, StatusBadge,
} from "@/components/ui";

const COD_LABELS = {
  not_applicable: "No COD",
  pending: "Pending",
  collected: "Collected",
  settled: "Settled",
};

const COD_CLASSES = {
  not_applicable: "bg-slate-100 text-slate-600 border-slate-200",
  pending: "bg-amber-50 text-amber-700 border-amber-200",
  collected: "bg-blue-50 text-blue-700 border-blue-200",
  settled: "bg-emerald-50 text-emerald-700 border-emerald-200",
};

const MANUAL_STATUSES = [
  ["picked_up", "Picked up by rider"],
  ["in_transit", "In transit"],
  ["out_for_delivery", "Out for delivery"],
  ["delivered", "Delivered"],
  ["returned", "Returned"],
];

export default function Delivery() {
  const { storeId, can } = useAuth();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState("in_transit");
  const [bookFor, setBookFor] = useState(null);
  const [statusFor, setStatusFor] = useState(null);
  const [failure, setFailure] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["shipments", storeId, filter],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filter === "in_transit") params.set("in_transit", "true");
      if (filter === "cod") params.set("cod_outstanding", "true");
      return (await api.get(`/shipments/?${params}`)).data;
    },
    enabled: Boolean(storeId),
  });

  const { data: ready } = useQuery({
    queryKey: ["ready-orders", storeId],
    queryFn: async () =>
      (await api.get("/orders/?status=confirmed&status=ready_to_ship")).data,
    enabled: Boolean(storeId) && can("book_shipments"),
  });

  const { data: couriers } = useQuery({
    queryKey: ["store-couriers", storeId],
    queryFn: async () => (await api.get("/couriers/store-couriers/")).data,
    enabled: Boolean(storeId),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["shipments"] });
    queryClient.invalidateQueries({ queryKey: ["ready-orders"] });
    queryClient.invalidateQueries({ queryKey: ["orders"] });
  };

  const shipments = data?.results || [];
  const pendingBooking = ready?.results || [];

  if (isLoading) return <PageLoader label="Loading deliveries" />;
  if (error) return <Alert>Could not load deliveries.</Alert>;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold">Delivery</h1>
        <p className="text-sm text-muted">Book parcels and follow them to the door.</p>
      </div>

      {failure && <Alert onDismiss={() => setFailure("")}>{failure}</Alert>}

      {can("book_shipments") && pendingBooking.length > 0 && (
        <section className="card p-4">
          <h2 className="mb-3 text-sm font-semibold">
            Waiting to be booked ({pendingBooking.length})
          </h2>
          <ul className="divide-y divide-line">
            {pendingBooking.map((order) => (
              <li key={order.id} className="flex flex-wrap items-center gap-3 py-2">
                <div className="min-w-0 flex-1">
                  <Link to={`/orders/${order.id}`}
                    className="text-sm font-medium text-brand-700 hover:underline">
                    {order.order_number}
                  </Link>
                  <p className="truncate text-xs text-muted">
                    {order.customer_name} &middot; {order.shipping_district}
                  </p>
                </div>
                <span className="text-sm tabular-nums">{money(order.cod_amount)}</span>
                <button type="button" className="btn-primary text-sm"
                  onClick={() => setBookFor(order)}>Book courier</button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="flex gap-2">
        {[
          ["in_transit", "In transit"],
          ["cod", "COD outstanding"],
          ["", "All"],
        ].map(([value, label]) => (
          <button key={value} type="button" onClick={() => setFilter(value)}
            className={`rounded-full border px-3 py-1 text-sm ${
              filter === value
                ? "border-brand-600 bg-brand-50 font-medium text-brand-700"
                : "border-line bg-white text-muted hover:text-ink"
            }`}>
            {label}
          </button>
        ))}
      </div>

      {shipments.length === 0 ? (
        <EmptyState title="No shipments here"
          description="Book a confirmed order and it will show up." />
      ) : (
        <div className="overflow-hidden rounded-xl border border-line bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-line bg-surface text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-2.5 font-medium">Consignment</th>
                <th className="px-4 py-2.5 font-medium">Order</th>
                <th className="px-4 py-2.5 font-medium">Courier</th>
                <th className="px-4 py-2.5 font-medium">Order status</th>
                <th className="px-4 py-2.5 font-medium">COD</th>
                <th className="px-4 py-2.5 text-right font-medium">Booked</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {shipments.map((shipment) => (
                <tr key={shipment.id} className="hover:bg-surface">
                  <td className="px-4 py-2.5">
                    <p className="font-medium">{shipment.consignment_id}</p>
                    <p className="text-xs text-muted">
                      {shipment.booking_mode === "api" ? "Booked via API" : "Manual"}
                    </p>
                  </td>
                  <td className="px-4 py-2.5">
                    <Link to={`/orders/${shipment.order}`}
                      className="text-brand-700 hover:underline">
                      {shipment.order_number}
                    </Link>
                    <p className="text-xs text-muted">{shipment.customer_name}</p>
                  </td>
                  <td className="px-4 py-2.5 text-muted">{shipment.courier_name}</td>
                  <td className="px-4 py-2.5">
                    <StatusBadge status={shipment.order_status} />
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs ${
                      COD_CLASSES[shipment.cod_status]
                    }`}>
                      {COD_LABELS[shipment.cod_status]}
                    </span>
                    <p className="mt-0.5 text-xs tabular-nums">
                      {money(shipment.cod_amount)}
                    </p>
                  </td>
                  <td className="px-4 py-2.5 text-right text-xs text-muted">
                    {relative(shipment.booked_at)}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    {can("update_shipment_status") && !shipment.delivered_at && (
                      <button type="button" className="text-sm text-brand-600 hover:underline"
                        onClick={() => setStatusFor(shipment)}>Update</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <BookModal order={bookFor} couriers={couriers || []}
        onClose={() => setBookFor(null)}
        onDone={() => { setBookFor(null); refresh(); }}
        onError={setFailure} />

      <StatusModal shipment={statusFor}
        onClose={() => setStatusFor(null)}
        onDone={() => { setStatusFor(null); refresh(); }}
        onError={setFailure} />
    </div>
  );
}

function BookModal({ order, couriers, onClose, onDone, onError }) {
  const [courierId, setCourierId] = useState("");
  const [consignment, setConsignment] = useState("");

  const selected = couriers.find((c) => String(c.id) === String(courierId));
  const needsManualId = selected && !selected.can_book_via_api;

  const book = useMutation({
    mutationFn: (body) => api.post("/shipments/book/", body),
    onSuccess: onDone,
    onError: (err) => onError(errorMessage(err)),
  });

  if (!order) return null;

  return (
    <Modal open title={`Book ${order.order_number}`} onClose={onClose}
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="btn-primary" disabled={!courierId || book.isPending}
            onClick={() => book.mutate({
              order: order.id,
              store_courier: Number(courierId),
              consignment_id: consignment,
            })}>
            {book.isPending && <Spinner className="h-4 w-4" />}
            Book parcel
          </button>
        </>
      }>
      <div className="space-y-4">
        <p className="text-sm text-muted">
          {order.customer_name} &middot; {order.shipping_district} &middot;{" "}
          {money(order.cod_amount)} to collect
        </p>

        <Field label="Courier" required>
          <select className="input" value={courierId}
            onChange={(e) => setCourierId(e.target.value)}>
            <option value="">Choose a courier...</option>
            {couriers.filter((c) => c.is_enabled).map((c) => (
              <option key={c.id} value={c.id}>
                {c.courier_name}
                {c.can_book_via_api ? " (API)" : " (manual)"}
              </option>
            ))}
          </select>
        </Field>

        {needsManualId && (
          <Field label="Consignment id" required
            hint="Book on the courier's own site, then paste their tracking number here.">
            <input className="input" value={consignment}
              onChange={(e) => setConsignment(e.target.value)} />
          </Field>
        )}

        {couriers.filter((c) => c.is_enabled).length === 0 && (
          <Alert tone="warn">
            No courier is set up yet. Add one under Settings first.
          </Alert>
        )}
      </div>
    </Modal>
  );
}

function StatusModal({ shipment, onClose, onDone, onError }) {
  const [rawStatus, setRawStatus] = useState("delivered");
  const [note, setNote] = useState("");

  const update = useMutation({
    mutationFn: (body) => api.post(`/shipments/${shipment.id}/status/`, body),
    onSuccess: onDone,
    onError: (err) => onError(errorMessage(err)),
  });

  if (!shipment) return null;

  return (
    <Modal open title={`Update ${shipment.consignment_id}`} onClose={onClose}
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="btn-primary" disabled={update.isPending}
            onClick={() => update.mutate({ raw_status: rawStatus, note })}>
            {update.isPending && <Spinner className="h-4 w-4" />}
            Save
          </button>
        </>
      }>
      <div className="space-y-4">
        <Field label="What happened?">
          <select className="input" value={rawStatus}
            onChange={(e) => setRawStatus(e.target.value)}>
            {MANUAL_STATUSES.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </Field>
        <Field label="Note">
          <input className="input" value={note} placeholder="Optional"
            onChange={(e) => setNote(e.target.value)} />
        </Field>
        {shipment.last_synced_at && (
          <p className="text-xs text-muted">
            Last synced {dateTime(shipment.last_synced_at)}
          </p>
        )}
      </div>
    </Modal>
  );
}
