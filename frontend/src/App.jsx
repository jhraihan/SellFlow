import { lazy, Suspense, useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { readTokens } from "@/lib/api";
import Layout from "@/components/Layout";
import { PageLoader } from "@/components/ui";

import Login from "@/pages/Login";

const Register = lazy(() => import("@/pages/Register"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const ResetPassword = lazy(() => import("@/pages/ResetPassword"));
const Onboarding = lazy(() => import("@/pages/Onboarding"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Orders = lazy(() => import("@/pages/Orders"));
const OrderNew = lazy(() => import("@/pages/OrderNew"));
const OrderDetail = lazy(() => import("@/pages/OrderDetail"));
const Products = lazy(() => import("@/pages/Products"));
const Customers = lazy(() => import("@/pages/Customers"));
const Delivery = lazy(() => import("@/pages/Delivery"));
const Returns = lazy(() => import("@/pages/Returns"));
const Payments = lazy(() => import("@/pages/Payments"));
const Analytics = lazy(() => import("@/pages/Analytics"));
const Settings = lazy(() => import("@/pages/Settings"));
const Notifications = lazy(() => import("@/pages/Notifications"));

function RequireAuth({ children }) {
  const { user, stores, ready } = useAuth();
  const location = useLocation();

  if (!ready) return <PageLoader label="Starting up" />;
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  if (stores.length === 0) return <Navigate to="/onboarding" replace />;
  return children;
}

function RedirectIfSignedIn({ children }) {
  const { user, stores, ready } = useAuth();
  if (!ready) return <PageLoader label="Starting up" />;
  if (user) return <Navigate to={stores.length ? "/dashboard" : "/onboarding"} replace />;
  return children;
}

export default function App() {
  const { bootstrap, ready } = useAuth();

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  if (!ready && readTokens()?.access) {
    return <PageLoader label="Starting up" />;
  }

  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route path="/login" element={<RedirectIfSignedIn><Login /></RedirectIfSignedIn>} />
        <Route path="/register" element={<RedirectIfSignedIn><Register /></RedirectIfSignedIn>} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password/:token" element={<ResetPassword />} />
        <Route path="/onboarding" element={<Onboarding />} />

        <Route element={<RequireAuth><Layout /></RequireAuth>}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/orders" element={<Orders />} />
          <Route path="/orders/new" element={<OrderNew />} />
          <Route path="/orders/:id" element={<OrderDetail />} />
          <Route path="/products" element={<Products />} />
          <Route path="/customers" element={<Customers />} />
          <Route path="/delivery" element={<Delivery />} />
          <Route path="/returns" element={<Returns />} />
          <Route path="/payments" element={<Payments />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/notifications" element={<Notifications />} />
        </Route>

        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Suspense>
  );
}
