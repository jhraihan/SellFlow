import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const NAV = [
  { to: "/dashboard", label: "Dashboard", cap: null },
  { to: "/orders", label: "Orders", cap: "view_orders", badge: "pending" },
  { to: "/products", label: "Products", cap: "view_products" },
  { to: "/customers", label: "Customers", cap: "view_customers" },
  { to: "/delivery", label: "Delivery", cap: "view_orders" },
  { to: "/returns", label: "Returns", cap: "view_orders" },
  { to: "/payments", label: "Payments", cap: "reconcile_cod" },
  { to: "/analytics", label: "Analytics", cap: "view_analytics" },
  { to: "/settings", label: "Settings", cap: null },
];

const MOBILE_NAV = ["/dashboard", "/orders", "/products", "/customers", "/settings"];

export function Logo({ className = "", tone = "text-ink" }) {
  return (
    <span className={`inline-flex items-baseline gap-1.5 ${tone} ${className}`}>
      <span className="font-display text-[1.7rem] italic leading-none">ShopFlow</span>
      <span className="text-[10px] font-medium uppercase tracking-eyebrow opacity-60">BD</span>
    </span>
  );
}

export default function Layout() {
  const { user, stores, storeId, selectStore, logout, can } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  const { data: stats } = useQuery({
    queryKey: ["order-stats", storeId],
    queryFn: async () => (await api.get("/orders/stats/")).data,
    enabled: Boolean(storeId),
    refetchInterval: 60000,
  });

  const { data: unread } = useQuery({
    queryKey: ["unread", storeId],
    queryFn: async () => (await api.get("/notifications/unread-count/")).data,
    enabled: Boolean(storeId),
    refetchInterval: 60000,
  });

  const pending = stats?.by_status?.pending || 0;
  const visible = NAV.filter((item) => !item.cap || can(item.cap));
  const storeName = stores.find((s) => s.store_id === storeId)?.store_name;

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="min-h-screen lg:flex">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-line bg-white lg:flex">
        <div className="px-7 pb-6 pt-7">
          <Logo />
        </div>

        {stores.length > 1 && (
          <div className="px-7 pb-4">
            <select
              className="input text-xs"
              value={storeId || ""}
              onChange={(e) => selectStore(Number(e.target.value))}
              aria-label="Select store"
            >
              {stores.map((s) => (
                <option key={s.store_id} value={s.store_id}>{s.store_name}</option>
              ))}
            </select>
          </div>
        )}

        <p className="eyebrow px-7 pb-2">Menu</p>
        <nav className="flex-1 overflow-y-auto px-7">
          {visible.map((item) => (
            <NavLink key={item.to} to={item.to}
              className={({ isActive }) =>
                `group flex items-center justify-between border-b border-line/70 py-[0.55rem] font-display text-[1.45rem] leading-tight tracking-tight transition ${
                  isActive ? "text-ink" : "text-ink/35 hover:text-ink/70"
                }`
              }>
              {({ isActive }) => (
                <>
                  <span>{isActive ? `{${item.label}}` : item.label}</span>
                  {item.badge === "pending" && pending > 0 && (
                    <span className="rounded-[3px] bg-butter px-1.5 font-sans text-[11px] font-medium text-ink">
                      {pending}
                    </span>
                  )}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="space-y-3 px-7 py-6">
          {can("manage_orders") && (
            <NavLink to="/orders/new" className="btn-primary w-full">
              New order
            </NavLink>
          )}
          <p className="text-[11px] leading-relaxed text-muted">
            Orders, couriers and cash on delivery, in one calm place.
          </p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-paper/85 px-4 py-3 backdrop-blur lg:px-10">
          <div className="flex min-w-0 items-center gap-3">
            <span className="lg:hidden"><Logo /></span>
            <span className="hidden min-w-0 items-baseline gap-2 lg:flex">
              <span className="eyebrow">Store</span>
              <span className="truncate font-display text-xl">{storeName}</span>
            </span>
          </div>

          <div className="flex items-center gap-3">
            <NavLink to="/notifications"
              className="rounded-[3px] border border-line bg-white px-3 py-1.5 text-xs text-ink transition hover:border-ink/40">
              Alerts ({unread?.unread ?? 0})
            </NavLink>

            <div className="relative">
              <button type="button" onClick={() => setMenuOpen((v) => !v)}
                className="flex items-center gap-2 text-sm text-ink">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-olive font-display text-base text-paper">
                  {(user?.full_name || user?.email || "A").trim().charAt(0).toUpperCase()}
                </span>
                <span className="hidden sm:inline">{user?.full_name?.split(" ")[0] || "Account"}</span>
              </button>
              {menuOpen && (
                <div className="absolute right-0 mt-2 w-48 rounded-[4px] border border-line bg-white py-1 shadow-xl shadow-olive-deep/10">
                  <p className="border-b border-line px-4 py-2 text-xs text-muted">{user?.email}</p>
                  <NavLink to="/settings" onClick={() => setMenuOpen(false)}
                    className="block px-4 py-2 text-sm hover:bg-paper">Settings</NavLink>
                  <button type="button" onClick={handleLogout}
                    className="block w-full px-4 py-2 text-left text-sm text-danger hover:bg-paper">
                    Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        <main className="flex-1 px-4 pb-28 pt-6 lg:px-10 lg:pb-12 lg:pt-8">
          <div className="mx-auto w-full max-w-7xl">
            <Outlet />
          </div>
        </main>

        <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-white/95 backdrop-blur lg:hidden">
          {visible
            .filter((item) => MOBILE_NAV.includes(item.to))
            .map((item) => (
              <NavLink key={item.to} to={item.to}
                className={({ isActive }) =>
                  `relative flex flex-1 flex-col items-center py-3 text-[11px] tracking-wide ${
                    isActive ? "font-medium text-ink" : "text-muted"
                  }`
                }>
                {({ isActive }) => (
                  <>
                    {isActive && <span className="absolute inset-x-5 top-0 h-[3px] bg-butter-deep" />}
                    {item.label}
                  </>
                )}
              </NavLink>
            ))}
        </nav>
      </div>
    </div>
  );
}
