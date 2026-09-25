import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart3, Bell, LayoutDashboard, LogOut, Package, Plus, Settings, ShoppingBag,
  Truck, Undo2, Users, Wallet,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const NAV = [
  { to: "/dashboard", label: "Dashboard", cap: null, icon: LayoutDashboard },
  { to: "/orders", label: "Orders", cap: "view_orders", badge: "pending", icon: ShoppingBag },
  { to: "/products", label: "Products", cap: "view_products", icon: Package },
  { to: "/customers", label: "Customers", cap: "view_customers", icon: Users },
  { to: "/delivery", label: "Delivery", cap: "view_orders", icon: Truck },
  { to: "/returns", label: "Returns", cap: "view_orders", icon: Undo2 },
  { to: "/payments", label: "Payments", cap: "reconcile_cod", icon: Wallet },
  { to: "/analytics", label: "Analytics", cap: "view_analytics", icon: BarChart3 },
  { to: "/settings", label: "Settings", cap: null, icon: Settings },
];

const MOBILE_NAV = ["/dashboard", "/orders", "/products", "/customers", "/settings"];

export function Logo({ className = "", dark = false }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-butter shadow-glow">
        <ShoppingBag className="h-[18px] w-[18px] text-ink" strokeWidth={2.4} />
      </span>
      <span className={`text-lg font-extrabold tracking-[-0.03em] ${dark ? "text-paper" : "text-ink"}`}>
        SellFlow
        <span className={`ml-1 align-super text-[10px] font-bold tracking-wider ${dark ? "text-butter" : "text-olive"}`}>BD</span>
      </span>
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
  const unreadCount = unread?.unread || 0;
  const visible = NAV.filter((item) => !item.cap || can(item.cap));
  const storeName = stores.find((s) => s.store_id === storeId)?.store_name;
  const initial = (user?.full_name || user?.email || "A").trim().charAt(0).toUpperCase();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="min-h-screen lg:flex">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col overflow-hidden bg-olive-deep text-paper lg:flex">
        <span className="pointer-events-none absolute -left-20 -top-20 h-56 w-56 rounded-full bg-butter/10 blur-3xl" />
        <div className="relative px-6 pb-6 pt-7">
          <Logo dark />
        </div>

        <div className="relative mx-4 mb-5 rounded-xl bg-white/[0.06] px-3.5 py-3 ring-1 ring-white/10">
          <p className="text-[10px] font-bold uppercase tracking-eyebrow text-paper/45">Store</p>
          {stores.length > 1 ? (
            <select
              className="mt-1 w-full cursor-pointer bg-transparent text-sm font-semibold text-paper focus:outline-none"
              value={storeId || ""}
              onChange={(e) => selectStore(Number(e.target.value))}
              aria-label="Select store"
            >
              {stores.map((s) => (
                <option key={s.store_id} value={s.store_id} className="text-ink">{s.store_name}</option>
              ))}
            </select>
          ) : (
            <p className="mt-0.5 truncate text-sm font-semibold">{storeName}</p>
          )}
        </div>

        <nav className="relative flex-1 space-y-1 overflow-y-auto px-4">
          {visible.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink key={item.to} to={item.to}
                className={({ isActive }) =>
                  `group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition ${
                    isActive
                      ? "bg-butter text-ink shadow-glow"
                      : "text-paper/65 hover:bg-white/[0.07] hover:text-paper"
                  }`
                }>
                <Icon className="h-[18px] w-[18px]" strokeWidth={2} />
                <span className="flex-1">{item.label}</span>
                {item.badge === "pending" && pending > 0 && (
                  <span className="rounded-full bg-clay px-2 py-0.5 text-[11px] font-bold text-white">
                    {pending}
                  </span>
                )}
              </NavLink>
            );
          })}
        </nav>

        {can("manage_orders") && (
          <div className="relative p-4">
            <div className="rounded-2xl bg-white/[0.06] p-4 ring-1 ring-white/10">
              <p className="text-sm font-bold">Got a new message?</p>
              <p className="mt-1 text-xs text-paper/55">Turn it into an order in under a minute.</p>
              <NavLink to="/orders/new" className="btn-primary mt-3 w-full">
                <Plus className="h-4 w-4" strokeWidth={2.5} />
                New order
              </NavLink>
            </div>
          </div>
        )}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line/80 bg-paper/80 px-4 py-3 backdrop-blur-md lg:px-10">
          <div className="flex min-w-0 items-center gap-3">
            <span className="lg:hidden"><Logo /></span>
            <p className="hidden text-sm text-muted lg:block">
              Welcome back, <span className="font-semibold text-ink">{user?.full_name?.split(" ")[0] || "there"}</span>
            </p>
          </div>

          <div className="flex items-center gap-2">
            {can("manage_orders") && (
              <NavLink to="/orders/new" className="btn-primary hidden px-3 py-1.5 sm:inline-flex lg:hidden">
                <Plus className="h-4 w-4" strokeWidth={2.5} />
                New
              </NavLink>
            )}
            <NavLink to="/notifications" aria-label={`Alerts, ${unreadCount} unread`}
              className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-line bg-white text-ink shadow-soft transition hover:border-ink/25">
              <Bell className="h-[18px] w-[18px]" strokeWidth={2} />
              {unreadCount > 0 && (
                <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-clay px-1 text-[10px] font-bold text-white ring-2 ring-paper">
                  {unreadCount}
                </span>
              )}
            </NavLink>

            <div className="relative">
              <button type="button" onClick={() => setMenuOpen((v) => !v)}
                className="flex items-center gap-2.5 rounded-xl border border-line bg-white py-1 pl-1 pr-3 shadow-soft transition hover:border-ink/25">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-olive to-olive-deep text-sm font-bold text-butter">
                  {initial}
                </span>
                <span className="hidden text-sm font-semibold sm:inline">{user?.full_name?.split(" ")[0] || "Account"}</span>
              </button>
              {menuOpen && (
                <div className="absolute right-0 mt-2 w-56 overflow-hidden rounded-xl border border-line bg-white shadow-lift">
                  <div className="border-b border-line bg-paper/60 px-4 py-3">
                    <p className="text-sm font-bold">{user?.full_name}</p>
                    <p className="truncate text-xs text-muted">{user?.email}</p>
                  </div>
                  <NavLink to="/settings" onClick={() => setMenuOpen(false)}
                    className="flex items-center gap-2.5 px-4 py-2.5 text-sm font-medium hover:bg-paper">
                    <Settings className="h-4 w-4 text-muted" /> Settings
                  </NavLink>
                  <button type="button" onClick={handleLogout}
                    className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-sm font-medium text-danger hover:bg-paper">
                    <LogOut className="h-4 w-4" /> Sign out
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

        <nav className="fixed inset-x-3 bottom-3 z-30 flex rounded-2xl bg-olive-deep p-1.5 shadow-lift lg:hidden">
          {visible
            .filter((item) => MOBILE_NAV.includes(item.to))
            .map((item) => {
              const Icon = item.icon;
              return (
                <NavLink key={item.to} to={item.to}
                  className={({ isActive }) =>
                    `flex flex-1 flex-col items-center gap-0.5 rounded-xl py-2 text-[10px] font-semibold transition ${
                      isActive ? "bg-butter text-ink" : "text-paper/60"
                    }`
                  }>
                  <Icon className="h-[18px] w-[18px]" strokeWidth={2} />
                  {item.label}
                </NavLink>
              );
            })}
        </nav>
      </div>
    </div>
  );
}
