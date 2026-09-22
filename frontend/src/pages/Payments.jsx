import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money, relative } from "@/lib/format";
import {
  Alert, EmptyState, Field, Modal, PageLoader, Spinner, StatCard,
} from "@/components/ui";

const MATCH_LABELS = {
  matched: "Matched",
  amount_mismatch: "Amount differs",
  unmatched: "No shipment found",
  already_settled: "Already settled",
};


export default function Payments() {
  const { storeId } = useAuth();
  const queryClient = useQueryClient();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [previewId, setPreviewId] = useState(null);
  const [failure, setFailure] = useState("");

  const { data: ledger, isLoading } = useQuery({
    queryKey: ["cod-ledger", storeId],
    queryFn: async () => (await api.get("/payments/cod-ledger/")).data,
    enabled: Boolean(storeId),
  });

  const { data: settlements } = useQuery({
    queryKey: ["settlements", storeId],
    queryFn: async () => (await api.get("/payments/settlements/")).data,
    enabled: Boolean(storeId),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["cod-ledger"] });
    queryClient.invalidateQueries({ queryKey: ["settlements"] });
    queryClient.invalidateQueries({ queryKey: ["shipments"] });
  };

  if (isLoading) return <PageLoader label="Loading the COD ledger" />;

  const rows = settlements?.results || [];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Payments</h1>
          <p className="text-sm text-muted">
            Where your cash is, and what the courier still owes you.
          </p>
        </div>
        <button type="button" className="btn-primary"
          onClick={() => setUploadOpen(true)}>Upload statement</button>
      </div>

      {failure && <Alert onDismiss={() => setFailure("")}>{failure}</Alert>}

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="In transit" value={money(ledger?.in_transit?.amount)}
          sub={`${ledger?.in_transit?.count ?? 0} parcels`} />
        <StatCard label="Collected, unsettled"
          value={money(ledger?.collected_unsettled?.amount)}
          sub={`${ledger?.collected_unsettled?.count ?? 0} parcels`} />
        <StatCard label="Overdue" value={money(ledger?.overdue?.amount)}
          tone={ledger?.overdue?.count > 0 ? "danger" : undefined}
          sub={`Delivered over ${ledger?.overdue_days ?? 7} days ago`} />
        <StatCard label="Settled" value={money(ledger?.settled?.amount)}
          tone="ok" sub={`${ledger?.settled?.count ?? 0} parcels`} />
      </section>

      {ledger?.shortfalls?.length > 0 && (
        <section className="card border-red-200 p-4">
          <h2 className="mb-1 text-sm font-semibold text-danger">
            Courier paid less than expected
          </h2>
          <p className="mb-3 text-xs text-muted">
            {money(ledger.shortfall_total)} short across{" "}
            {ledger.shortfalls.length} parcel(s).
          </p>
          <ul className="divide-y divide-line text-sm">
            {ledger.shortfalls.map((row) => (
              <li key={row.consignment_id} className="flex justify-between gap-3 py-1.5">
                <span className="min-w-0 truncate">
                  {row.order_number || row.consignment_id}
                </span>
                <span className="shrink-0 tabular-nums">
                  expected {money(row.expected)} &middot; got {money(row.received)}
                  <span className="ml-2 font-medium text-danger">
                    -{money(row.difference)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2 className="mb-3 text-sm font-semibold">Courier statements</h2>
        {rows.length === 0 ? (
          <EmptyState title="No statements uploaded"
            description="Upload the CSV your courier sends and we will match it to your shipments." />
        ) : (
          <div className="overflow-hidden rounded-xl border border-line bg-white">
            <table className="w-full text-sm">
              <thead className="border-b border-line bg-surface text-left text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Statement</th>
                  <th className="px-4 py-2.5 font-medium">Courier</th>
                  <th className="px-4 py-2.5 text-right font-medium">Matched</th>
                  <th className="px-4 py-2.5 text-right font-medium">Needs review</th>
                  <th className="px-4 py-2.5 text-right font-medium">Total</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((row) => (
                  <tr key={row.id} className="hover:bg-surface">
                    <td className="px-4 py-2.5">
                      <p className="font-medium">
                        {row.statement_reference || `#${row.id}`}
                      </p>
                      <p className="text-xs text-muted">{relative(row.created_at)}</p>
                    </td>
                    <td className="px-4 py-2.5 text-muted">{row.courier_name}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-ok">
                      {row.matched_count}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      {row.mismatch_count + row.unmatched_count > 0 ? (
                        <span className="text-warn">
                          {row.mismatch_count + row.unmatched_count}
                        </span>
                      ) : "0"}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      {money(row.total_amount)}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs ${
                        row.status === "committed"
                          ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                          : "border-amber-200 bg-amber-50 text-amber-700"
                      }`}>
                        {row.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <button type="button" className="text-sm text-brand-600 hover:underline"
                        onClick={() => setPreviewId(row.id)}>Review</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <UploadModal open={uploadOpen} onClose={() => setUploadOpen(false)}
        onDone={(id) => { setUploadOpen(false); refresh(); setPreviewId(id); }}
        onError={setFailure} />

      <PreviewModal settlementId={previewId} onClose={() => setPreviewId(null)}
        onDone={() => { setPreviewId(null); refresh(); }} onError={setFailure} />
    </div>
  );
}

function UploadModal({ open, onClose, onDone, onError }) {
  const { storeId } = useAuth();
  const [courierId, setCourierId] = useState("");
  const [reference, setReference] = useState("");
  const fileRef = useRef(null);

  const { data: couriers } = useQuery({
    queryKey: ["store-couriers", storeId],
    queryFn: async () => (await api.get("/couriers/store-couriers/")).data,
    enabled: open && Boolean(storeId),
  });

  const upload = useMutation({
    mutationFn: (formData) =>
      api.post("/payments/settlements/", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      }),
    onSuccess: (response) => onDone(response.data.id),
    onError: (err) => onError(errorMessage(err)),
  });

  if (!open) return null;

  function submit() {
    const file = fileRef.current?.files?.[0];
    if (!file || !courierId) return;
    const formData = new FormData();
    formData.append("file", file);
    formData.append("store_courier", courierId);
    if (reference) formData.append("statement_reference", reference);
    upload.mutate(formData);
  }

  return (
    <Modal open title="Upload a courier statement" onClose={onClose}
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="btn-primary" disabled={upload.isPending}
            onClick={submit}>
            {upload.isPending && <Spinner className="h-4 w-4" />}
            Upload and match
          </button>
        </>
      }>
      <div className="space-y-4">
        <Alert tone="info">
          Nothing is settled until you review and confirm. This only matches rows
          to your shipments.
        </Alert>

        <Field label="Courier" required>
          <select className="input" value={courierId}
            onChange={(e) => setCourierId(e.target.value)}>
            <option value="">Choose a courier...</option>
            {(couriers || []).map((c) => (
              <option key={c.id} value={c.id}>{c.courier_name}</option>
            ))}
          </select>
        </Field>

        <Field label="CSV file" required
          hint="The file your courier sends. Column names can vary.">
          <input ref={fileRef} type="file" accept=".csv,text/csv" className="input" />
        </Field>

        <Field label="Statement reference"
          hint="Something you will recognise later, e.g. OCT-W1.">
          <input className="input" value={reference}
            onChange={(e) => setReference(e.target.value)} />
        </Field>
      </div>
    </Modal>
  );
}

function PreviewModal({ settlementId, onClose, onDone, onError }) {
  const [includeMismatches, setIncludeMismatches] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["settlement-preview", settlementId],
    queryFn: async () =>
      (await api.get(`/payments/settlements/${settlementId}/preview/`)).data,
    enabled: Boolean(settlementId),
  });

  const commit = useMutation({
    mutationFn: () =>
      api.post(`/payments/settlements/${settlementId}/commit/`, {
        include_mismatches: includeMismatches,
      }),
    onSuccess: onDone,
    onError: (err) => onError(errorMessage(err)),
  });

  if (!settlementId) return null;

  const buckets = data?.buckets || {};
  const counts = data?.counts || {};
  const committed = data?.settlement?.status === "committed";

  return (
    <Modal open title="Review the statement" onClose={onClose}
      footer={
        committed ? (
          <button type="button" className="btn-secondary" onClick={onClose}>Close</button>
        ) : (
          <>
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="button" className="btn-primary" disabled={commit.isPending}
              onClick={() => commit.mutate()}>
              {commit.isPending && <Spinner className="h-4 w-4" />}
              Settle {includeMismatches
                ? (counts.matched || 0) + (counts.amount_mismatch || 0)
                : counts.matched || 0} row(s)
            </button>
          </>
        )
      }>
      {isLoading ? (
        <PageLoader label="Matching rows" />
      ) : (
        <div className="space-y-4">
          {committed && (
            <Alert tone="ok">This statement has already been settled.</Alert>
          )}

          <div className="grid grid-cols-2 gap-2 text-sm">
            {Object.entries(MATCH_LABELS).map(([key, label]) => (
              <div key={key} className="rounded-lg border border-line px-3 py-2">
                <p className="text-xs text-muted">{label}</p>
                <p className="text-lg font-semibold tabular-nums">
                  {counts[key] || 0}
                </p>
              </div>
            ))}
          </div>

          {counts.amount_mismatch > 0 && !committed && (
            <Alert tone="warn" title="Some amounts do not match">
              <ul className="mt-1 space-y-1 text-xs">
                {(buckets.amount_mismatch || []).slice(0, 5).map((line) => (
                  <li key={line.id}>
                    {line.consignment_id}: courier says {money(line.collected_amount)},
                    order expects {money(line.expected_amount)}
                  </li>
                ))}
              </ul>
              <label className="mt-2 flex items-center gap-2 text-xs">
                <input type="checkbox" checked={includeMismatches}
                  onChange={(e) => setIncludeMismatches(e.target.checked)} />
                Settle these anyway and record the shortfall
              </label>
            </Alert>
          )}

          {counts.unmatched > 0 && (
            <Alert tone="danger" title="Rows with no matching shipment">
              <ul className="mt-1 space-y-1 text-xs">
                {(buckets.unmatched || []).slice(0, 5).map((line) => (
                  <li key={line.id}>
                    {line.consignment_id || "(no consignment id)"} -{" "}
                    {money(line.collected_amount)}
                  </li>
                ))}
              </ul>
              <p className="mt-1 text-xs">These are skipped.</p>
            </Alert>
          )}
        </div>
      )}
    </Modal>
  );
}
