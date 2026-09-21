import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { readTokens } from "@/lib/api";
import Layout from "@/components/Layout";
import { PageLoader } from "@/components/ui";

import Login from "@/pages/Login";
import Register from "@/pages/Register";
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";
import Onboarding from "@/pages/Onboarding";
import Dashboard from "@/pages/Dashboard";
import Orders from "@/pages/Orders";
import OrderNew from "@/pages/OrderNew";
import OrderDetail from "@/pages/OrderDetail";
import Products from "@/pages/Products";
import Customers from "@/pages/Customers";
import Notifications from "@/pages/Notifications";
import Placeholder from "@/pages/Placeholder";

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
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/delivery" element={
          <Placeholder title="Delivery"
            description="Shipment board and courier booking come next." />
        } />
        <Route path="/returns" element={
          <Placeholder title="Returns"
            description="Return processing comes next." />
        } />
        <Route path="/payments" element={
          <Placeholder title="Payments"
            description="COD ledger and settlement import come next." />
        } />
        <Route path="/analytics" element={
          <Placeholder title="Analytics"
            description="Profit and performance reports come next." />
        } />
        <Route path="/settings" element={
          <Placeholder title="Settings"
            description="Store profile, staff and couriers come next." />
        } />
      </Route>

      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
