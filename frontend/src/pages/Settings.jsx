import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateOnly, money } from "@/lib/format";
import { Alert, Field, Modal, PageHeader, PageLoader, Spinner } from "@/components/ui";

const TABS = [
  ["store", "Store"],
  ["delivery", "Delivery charges"],
  ["couriers", "Couriers"],
  ["staff", "Staff"],
  ["plan", "Plan"],
];

const ROLES = [
  ["manager", "Manager"],
  ["order_staff", "Order Staff"],
  ["delivery_staff", "Delivery Staff"],
  ["accountant", "Accountant"],
];

export default function Settings() {
  const { can } = useAuth();
  const [tab, setTab] = useState("store");
  const [notice, setNotice] = useState("");
  const [failure, setFailure] = useState("");

  const visible = TABS.filter(([key]) => {
    if (key === "staff") return can("manage_staff");
    if (key === "couriers") return can("manage_courier_credentials");
    if (key === "plan") return can("manage_billing");
    if (key === "delivery") return can("manage_settings");
    return true;
  });

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Configuration" title="Settings" note="How your store runs" />

      <div className="grid grid-cols-1 gap-8 rounded-[4px] border border-line bg-white p-5 lg:grid-cols-[17rem_1fr] lg:p-10">
        <nav aria-label="Settings sections" className="min-w-0">
          <p className="eyebrow mb-3">Sections</p>
          <ul className="flex gap-2 overflow-x-auto lg:block">
            {visible.map(([key, label]) => (
              <li key={key} className="shrink-0 lg:border-b lg:border-line">
                <button type="button" onClick={() => setTab(key)}
                  className={`w-full py-1 pr-4 text-left font-display text-3xl leading-tight tracking-tight transition lg:py-2.5 lg:text-[2.6rem] ${
                    tab === key ? "text-ink" : "text-ink/25 hover:text-ink/55"
                  }`}>
                  {tab === key ? `{${label}}` : label}
                </button>
              </li>
            ))}
          </ul>
        </nav>

        <div className="min-w-0 space-y-4">
          {notice && <Alert tone="ok" onDismiss={() => setNotice("")}>{notice}</Alert>}
          {failure && <Alert onDismiss={() => setFailure("")}>{failure}</Alert>}

          {tab === "store" && <StoreTab onSaved={setNotice} onError={setFailure} />}
          {tab === "delivery" && <DeliveryTab onSaved={setNotice} onError={setFailure} />}
          {tab === "couriers" && <CouriersTab onSaved={setNotice} onError={setFailure} />}
          {tab === "staff" && <StaffTab onSaved={setNotice} onError={setFailure} />}
          {tab === "plan" && <PlanTab onSaved={setNotice} onError={setFailure} />}
        </div>
      </div>
    </div>
  );
}

function StoreTab({ onSaved, onError }) {
  const { storeId, can } = useAuth();
  const queryClient = useQueryClient();
  const [form, setForm] = useState(null);

  const { data } = useQuery({
    queryKey: ["store", storeId],
    queryFn: async () => (await api.get(`/stores/${storeId}/`)).data,
    enabled: Boolean(storeId),
  });

  const current = form || (data && {
    name: data.name || "",
    contact_phone: data.contact_phone || "",
    contact_email: data.contact_email || "",
    district: data.district || "",
    address_line: data.address_line || "",
    facebook_page_url: data.facebook_page_url || "",
  });

  const save = useMutation({
    mutationFn: (body) => api.patch(`/stores/${storeId}/`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["store"] });
      onSaved("Store details saved.");
    },
    onError: (err) => onError(errorMessage(err)),
  });

  if (!current) return <PageLoader label="Loading store" />;

  const editable = can("manage_settings");

  return (
    <section className="space-y-5">
      <Field label="Store name">
        <input className="input" value={current.name} disabled={!editable}
          onChange={(e) => setForm({ ...current, name: e.target.value })} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Contact phone">
          <input className="input" value={current.contact_phone} disabled={!editable}
            onChange={(e) => setForm({ ...current, contact_phone: e.target.value })} />
        </Field>
        <Field label="Contact email">
          <input className="input" value={current.contact_email} disabled={!editable}
            onChange={(e) => setForm({ ...current, contact_email: e.target.value })} />
        </Field>
      </div>
      <Field label="District">
        <input className="input" value={current.district} disabled={!editable}
          onChange={(e) => setForm({ ...current, district: e.target.value })} />
      </Field>
      <Field label="Address">
        <input className="input" value={current.address_line} disabled={!editable}
          onChange={(e) => setForm({ ...current, address_line: e.target.value })} />
      </Field>
      <Field label="Facebook page">
        <input className="input" value={current.facebook_page_url} disabled={!editable}
          onChange={(e) => setForm({ ...current, facebook_page_url: e.target.value })} />
      </Field>

      {editable && (
        <button type="button" className="btn-primary" disabled={save.isPending}
          onClick={() => save.mutate(current)}>
          {save.isPending && <Spinner className="h-4 w-4" />}
          Save changes
        </button>
      )}
    </section>
  );
}

function DeliveryTab({ onSaved, onError }) {
  const { storeId } = useAuth();
  const queryClient = useQueryClient();
  const [form, setForm] = useState(null);

  const { data } = useQuery({
    queryKey: ["store-settings", storeId],
    queryFn: async () => (await api.get(`/stores/${storeId}/settings/`)).data,
    enabled: Boolean(storeId),
  });

  const current = form || (data && {
    delivery_charge_inside_dhaka: data.delivery_charge_inside_dhaka || "0",
    delivery_charge_outside_dhaka: data.delivery_charge_outside_dhaka || "0",
    free_delivery_threshold: data.free_delivery_threshold || "",
    cod_overdue_days: data.cod_overdue_days ?? 7,
    fraud_return_count_threshold: data.fraud_return_count_threshold ?? 3,
  });

  const save = useMutation({
    mutationFn: (body) => api.patch(`/stores/${storeId}/settings/`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["store-settings"] });
      onSaved("Delivery settings saved.");
    },
    onError: (err) => onError(errorMessage(err)),
  });

  if (!current) return <PageLoader label="Loading settings" />;

  return (
    <section className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Inside Dhaka">
          <input className="input" inputMode="decimal"
            value={current.delivery_charge_inside_dhaka}
            onChange={(e) => setForm({
              ...current, delivery_charge_inside_dhaka: e.target.value,
            })} />
        </Field>
        <Field label="Outside Dhaka">
          <input className="input" inputMode="decimal"
            value={current.delivery_charge_outside_dhaka}
            onChange={(e) => setForm({
              ...current, delivery_charge_outside_dhaka: e.target.value,
            })} />
        </Field>
      </div>

      <Field label="Free delivery above"
        hint="Leave blank to always charge for delivery.">
        <input className="input" inputMode="decimal"
          value={current.free_delivery_threshold || ""}
          onChange={(e) => setForm({
            ...current, free_delivery_threshold: e.target.value || null,
          })} />
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="COD counts as overdue after"
          hint="Days since delivery with no settlement.">
          <input type="number" min={1} className="input" value={current.cod_overdue_days}
            onChange={(e) => setForm({
              ...current, cod_overdue_days: Number(e.target.value),
            })} />
        </Field>
        <Field label="Flag a customer after this many returns">
          <input type="number" min={1} className="input"
            value={current.fraud_return_count_threshold}
            onChange={(e) => setForm({
              ...current, fraud_return_count_threshold: Number(e.target.value),
            })} />
        </Field>
      </div>

      <button type="button" className="btn-primary" disabled={save.isPending}
        onClick={() => save.mutate(current)}>
        {save.isPending && <Spinner className="h-4 w-4" />}
        Save changes
      </button>
    </section>
  );
}

function CouriersTab({ onSaved, onError }) {
  const { storeId } = useAuth();
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);

  const { data: linked, isLoading } = useQuery({
    queryKey: ["store-couriers", storeId],
    queryFn: async () => (await api.get("/couriers/store-couriers/")).data,
    enabled: Boolean(storeId),
  });

  const { data: available } = useQuery({
    queryKey: ["couriers"],
    queryFn: async () => (await api.get("/couriers/")).data,
  });

  const verify = useMutation({
    mutationFn: (id) => api.post(`/couriers/store-couriers/${id}/verify/`, {}),
    onSuccess: (response) => onSaved(response.data.message),
    onError: (err) => onError(errorMessage(err)),
  });

  if (isLoading) return <PageLoader label="Loading couriers" />;

  const rows = linked || [];
  const usedIds = new Set(rows.map((r) => r.courier));
  const unused = (available || []).filter((c) => !usedIds.has(c.id));

  return (
    <section className="space-y-4">
      <div className="card divide-y divide-line">
        {rows.length === 0 && (
          <p className="p-4 text-sm text-muted">
            No courier set up yet. Add one to start booking parcels.
          </p>
        )}
        {rows.map((row) => (
          <div key={row.id} className="flex flex-wrap items-center gap-3 p-4">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">{row.courier_name}</p>
              <p className="text-xs text-muted">
                {row.can_book_via_api
                  ? "Ready for one-click booking"
                  : row.supports_api
                    ? "Add credentials to book automatically"
                    : "Manual booking"}
                {row.is_default && " · default"}
              </p>
              {row.last_error && (
                <p className="text-xs text-danger">{row.last_error}</p>
              )}
            </div>
            <button type="button" className="btn-secondary text-sm"
              disabled={verify.isPending}
              onClick={() => verify.mutate(row.id)}>Test</button>
          </div>
        ))}
      </div>

      {unused.length > 0 && (
        <button type="button" className="btn-secondary"
          onClick={() => setAddOpen(true)}>+ Add a courier</button>
      )}

      <AddCourierModal open={addOpen} couriers={unused}
        onClose={() => setAddOpen(false)}
        onDone={() => {
          setAddOpen(false);
          queryClient.invalidateQueries({ queryKey: ["store-couriers"] });
          onSaved("Courier added.");
        }}
        onError={onError} />
    </section>
  );
}

function AddCourierModal({ open, couriers, onClose, onDone, onError }) {
  const [courierId, setCourierId] = useState("");
  const [credentials, setCredentials] = useState({});

  const selected = couriers.find((c) => String(c.id) === String(courierId));
  const required = selected?.required_credentials || [];

  const create = useMutation({
    mutationFn: (body) => api.post("/couriers/store-couriers/", body),
    onSuccess: onDone,
    onError: (err) => onError(errorMessage(err)),
  });

  if (!open) return null;

  return (
    <Modal open title="Add a courier" onClose={onClose}
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="btn-primary"
            disabled={!courierId || create.isPending}
            onClick={() => create.mutate({
              courier: Number(courierId),
              credentials: required.length ? credentials : undefined,
            })}>
            {create.isPending && <Spinner className="h-4 w-4" />}
            Add courier
          </button>
        </>
      }>
      <div className="space-y-4">
        <Field label="Courier" required>
          <select className="input" value={courierId}
            onChange={(e) => { setCourierId(e.target.value); setCredentials({}); }}>
            <option value="">Choose...</option>
            {couriers.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </Field>

        {required.length > 0 && (
          <>
            <Alert tone="info">
              These are stored encrypted and never shown again.
            </Alert>
            {required.map((name) => (
              <Field key={name} label={name.replace(/_/g, " ")} required>
                <input className="input" type="password" autoComplete="off"
                  value={credentials[name] || ""}
                  onChange={(e) => setCredentials({
                    ...credentials, [name]: e.target.value,
                  })} />
              </Field>
            ))}
          </>
        )}

        {selected && required.length === 0 && (
          <p className="text-sm text-muted">
            This courier needs no credentials. You will enter the consignment id
            by hand when booking.
          </p>
        )}
      </div>
    </Modal>
  );
}

function StaffTab({ onSaved, onError }) {
  const { storeId } = useAuth();
  const queryClient = useQueryClient();
  const [inviteOpen, setInviteOpen] = useState(false);

  const { data: staff, isLoading } = useQuery({
    queryKey: ["staff", storeId],
    queryFn: async () => (await api.get("/stores/staff/")).data,
    enabled: Boolean(storeId),
  });

  const { data: invites } = useQuery({
    queryKey: ["invitations", storeId],
    queryFn: async () => (await api.get("/stores/invitations/")).data,
    enabled: Boolean(storeId),
  });

  const remove = useMutation({
    mutationFn: (id) => api.delete(`/stores/staff/${id}/`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["staff"] });
      onSaved("Access removed.");
    },
    onError: (err) => onError(errorMessage(err)),
  });

  if (isLoading) return <PageLoader label="Loading staff" />;

  const members = staff?.results || [];
  const pending = (invites?.results || []).filter((i) => i.is_usable);

  return (
    <section className="space-y-4">
      <div className="card divide-y divide-line">
        {members.map((member) => (
          <div key={member.id} className="flex flex-wrap items-center gap-3 p-4">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">{member.full_name || member.email}</p>
              <p className="text-xs text-muted">
                {member.email} &middot; {member.role.replace(/_/g, " ")}
                {!member.is_active && " · removed"}
              </p>
            </div>
            {member.role !== "owner" && member.is_active && (
              <button type="button" className="text-sm text-danger hover:underline"
                onClick={() => remove.mutate(member.id)}>Remove</button>
            )}
          </div>
        ))}
      </div>

      {pending.length > 0 && (
        <div className="card p-4">
          <h2 className="mb-2 section-title">Pending invitations</h2>
          <ul className="space-y-1 text-sm">
            {pending.map((invite) => (
              <li key={invite.id} className="flex justify-between">
                <span>{invite.email}</span>
                <span className="text-muted">{invite.role.replace(/_/g, " ")}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <button type="button" className="btn-secondary"
        onClick={() => setInviteOpen(true)}>+ Invite someone</button>

      <InviteModal open={inviteOpen} onClose={() => setInviteOpen(false)}
        onDone={() => {
          setInviteOpen(false);
          queryClient.invalidateQueries({ queryKey: ["invitations"] });
          onSaved("Invitation sent.");
        }}
        onError={onError} />
    </section>
  );
}

function InviteModal({ open, onClose, onDone, onError }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("order_staff");

  const invite = useMutation({
    mutationFn: (body) => api.post("/stores/invitations/", body),
    onSuccess: onDone,
    onError: (err) => onError(errorMessage(err)),
  });

  if (!open) return null;

  return (
    <Modal open title="Invite someone to your store" onClose={onClose}
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="btn-primary"
            disabled={!email || invite.isPending}
            onClick={() => invite.mutate({ email, role })}>
            {invite.isPending && <Spinner className="h-4 w-4" />}
            Send invitation
          </button>
        </>
      }>
      <div className="space-y-4">
        <Field label="Email" required>
          <input type="email" className="input" value={email}
            onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Role" required
          hint="Order staff cannot see cost prices or profit.">
          <select className="input" value={role}
            onChange={(e) => setRole(e.target.value)}>
            {ROLES.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </Field>
        <p className="text-xs text-muted">
          The invitation link expires in 72 hours.
        </p>
      </div>
    </Modal>
  );
}

function PlanTab({ onSaved, onError }) {
  const { storeId } = useAuth();
  const queryClient = useQueryClient();

  const { data: subscription, isLoading } = useQuery({
    queryKey: ["subscription", storeId],
    queryFn: async () => (await api.get("/billing/subscription/")).data,
    enabled: Boolean(storeId),
  });

  const { data: plans } = useQuery({
    queryKey: ["plans"],
    queryFn: async () => (await api.get("/billing/plans/")).data,
  });

  const activate = useMutation({
    mutationFn: (code) => api.post("/billing/activate/", { plan: code }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subscription"] });
      onSaved("Plan updated.");
    },
    onError: (err) => onError(errorMessage(err)),
  });

  if (isLoading) return <PageLoader label="Loading your plan" />;

  return (
    <section className="space-y-4">
      <div className="card p-4">
        <h2 className="section-title">
          You are on {subscription?.plan?.name}
        </h2>
        {subscription?.plan?.order_limit ? (
          <>
            <p className="mt-1 text-sm text-muted">
              {subscription.orders_used} of {subscription.plan.order_limit} orders
              used this period
              {subscription.period_end &&
                ` · resets ${dateOnly(subscription.period_end)}`}
            </p>
            <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-surface">
              <div className={`h-full rounded-full ${
                subscription.is_over_limit ? "bg-danger"
                  : subscription.is_near_limit ? "bg-warn" : "bg-olive"
              }`} style={{
                width: `${Math.min(Number(subscription.usage_percent), 100)}%`,
              }} />
            </div>
            {subscription.is_near_limit && !subscription.is_over_limit && (
              <p className="mt-2 text-sm text-warn">
                You are close to the limit. Upgrade to keep taking orders.
              </p>
            )}
            {subscription.is_over_limit && (
              <p className="mt-2 text-sm text-danger">
                You have used the whole allowance. New orders are blocked until
                you upgrade or the period resets.
              </p>
            )}
          </>
        ) : (
          <p className="mt-1 text-sm text-muted">Unlimited orders.</p>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {(plans || []).map((plan) => {
          const current = plan.code === subscription?.plan?.code;
          return (
            <div key={plan.id}
              className={`card p-4 ${current ? "border-brand-600" : ""}`}>
              <div className="flex items-baseline justify-between">
                <h3 className="text-sm font-semibold">{plan.name}</h3>
                <span className="text-sm tabular-nums">
                  {Number(plan.monthly_price) === 0
                    ? "Free" : `${money(plan.monthly_price)}/mo`}
                </span>
              </div>
              <ul className="mt-2 space-y-0.5 text-xs text-muted">
                <li>
                  {plan.order_limit
                    ? `${plan.order_limit} orders a month`
                    : "Unlimited orders"}
                </li>
                <li>{plan.staff_limit} user(s)</li>
                <li>
                  {plan.allows_api_courier
                    ? "One-click courier booking"
                    : "Manual courier booking"}
                </li>
              </ul>
              {current ? (
                <p className="mt-3 text-xs font-medium text-brand-700">
                  Your current plan
                </p>
              ) : (
                <button type="button" className="btn-secondary mt-3 w-full text-sm"
                  disabled={activate.isPending}
                  onClick={() => activate.mutate(plan.code)}>
                  Switch to {plan.name}
                </button>
              )}
            </div>
          );
        })}
      </div>

      <p className="text-xs text-muted">
        Payment is arranged directly with us by bank or bKash for now.
      </p>
    </section>
  );
}
