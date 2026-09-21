import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Alert, Field, Spinner } from "@/components/ui";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [failure, setFailure] = useState("");

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm();

  async function onSubmit(values) {
    setFailure("");
    try {
      const { hasStore } = await login(values.email, values.password);
      navigate(hasStore ? "/dashboard" : "/onboarding");
    } catch (error) {
      setFailure(
        error?.response?.status === 401
          ? "That email and password do not match."
          : errorMessage(error),
      );
    }
  }

  return (
    <AuthShell title="Sign in" subtitle="Manage your orders, deliveries and cash.">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {failure && <Alert>{failure}</Alert>}

        <Field label="Email" required error={errors.email?.message}>
          <input type="email" autoComplete="email" autoFocus className="input"
            {...register("email", { required: "Enter your email." })} />
        </Field>

        <Field label="Password" required error={errors.password?.message}>
          <input type="password" autoComplete="current-password" className="input"
            {...register("password", { required: "Enter your password." })} />
        </Field>

        <button type="submit" disabled={isSubmitting} className="btn-primary w-full">
          {isSubmitting && <Spinner className="h-4 w-4" />}
          Sign in
        </button>

        <div className="flex items-center justify-between text-sm">
          <Link to="/forgot-password" className="text-brand-600 hover:underline">
            Forgot password?
          </Link>
          <Link to="/register" className="text-brand-600 hover:underline">
            Create an account
          </Link>
        </div>
      </form>
    </AuthShell>
  );
}

export function AuthShell({ title, subtitle, children }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <p className="text-lg font-semibold">ShopFlow BD</p>
          <h1 className="mt-4 text-xl font-semibold">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
        </div>
        <div className="card p-6">{children}</div>
      </div>
    </div>
  );
}
