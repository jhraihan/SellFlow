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

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="min-h-screen lg:flex">
      <aside className="hidden w-56 shrink-0 border-r border-line bg-white lg:flex lg:flex-col">
        <div className="px-5 py-4">
          <p className="text-sm font-semibold">ShopFlow BD</p>
        </div>

        {stores.length > 1 && (
          <div className="px-3 pb-3">
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

        <nav className="flex-1 space-y-0.5 px-3">
          {visible.map((item) => (
            <NavLink key={item.to} to={item.to}
              className={({ isActive }) =>
                `flex items-center justify-between rounded-lg px-3 py-2 text-sm ${
                  isActive
                    ? "bg-brand-50 font-medium text-brand-700"
                    : "text-ink hover:bg-surface"
                }`
              }>
              <span>{item.label}</span>
              {item.badge === "pending" && pending > 0 && (
                <span className="rounded-full bg-amber-100 px-2 text-xs font-medium text-amber-700">
                  {pending}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-line p-3">
          {can("manage_orders") && (
            <NavLink to="/orders/new" className="btn-primary w-full text-sm">
              + New Order
            </NavLink>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-white px-4 py-3">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold lg:hidden">ShopFlow BD</span>
            <span className="hidden text-sm text-muted lg:inline">
              {stores.find((s) => s.store_id === storeId)?.store_name}
            </span>
          </div>

          <div className="flex items-center gap-3">
            <NavLink to="/notifications" className="relative text-sm text-muted hover:text-ink">
              Alerts
              {unread?.unread > 0 && (
                <span className="absolute -right-3 -top-1 rounded-full bg-danger px-1.5 text-[10px] font-medium text-white">
                  {unread.unread}
                </span>
              )}
            </NavLink>

            <div className="relative">
              <button type="button" onClick={() => setMenuOpen((v) => !v)}
                className="text-sm text-ink hover:text-brand-600">
                {user?.full_name?.split(" ")[0] || "Account"}
              </button>
              {menuOpen && (
                <div className="absolute right-0 mt-2 w-44 rounded-lg border border-line bg-white py-1 shadow-lg">
                  <NavLink to="/settings" onClick={() => setMenuOpen(false)}
                    className="block px-3 py-2 text-sm hover:bg-surface">Settings</NavLink>
                  <button type="button" onClick={handleLogout}
                    className="block w-full px-3 py-2 text-left text-sm text-danger hover:bg-surface">
                    Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        <main className="flex-1 px-4 pb-24 pt-5 lg:px-6 lg:pb-8">
          <Outlet />
        </main>

        <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-white lg:hidden">
          {visible
            .filter((item) => MOBILE_NAV.includes(item.to))
            .map((item) => (
              <NavLink key={item.to} to={item.to}
                className={({ isActive }) =>
                  `flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] ${
                    isActive ? "text-brand-700" : "text-muted"
                  }`
                }>
                {item.label}
              </NavLink>
            ))}
        </nav>
      </div>
    </div>
  );
}
