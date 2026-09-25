import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Alert, Field, Spinner } from "@/components/ui";
import { Logo } from "@/components/Layout";

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
    <AuthShell eyebrow="Welcome back" title="Sign in"
      subtitle="Manage your orders, deliveries and cash.">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
        {failure && <Alert>{failure}</Alert>}

        <Field label="Email" required error={errors.email?.message}>
          <input type="email" autoComplete="email" autoFocus className="input"
            {...register("email", { required: "Enter your email." })} />
        </Field>

        <Field label="Password" required error={errors.password?.message}>
          <input type="password" autoComplete="current-password" className="input"
            {...register("password", { required: "Enter your password." })} />
        </Field>

        <button type="submit" disabled={isSubmitting} className="btn-primary w-full py-2.5">
          {isSubmitting && <Spinner className="h-4 w-4" />}
          Sign in
        </button>

        <div className="flex items-center justify-between pt-1 text-sm">
          <Link to="/forgot-password" className="link">Forgot password?</Link>
          <Link to="/register" className="link">Create an account</Link>
        </div>
      </form>
    </AuthShell>
  );
}

function Scene() {
  return (
    <div className="pointer-events-none absolute inset-0" aria-hidden="true">
      <div className="absolute inset-0 bg-[linear-gradient(165deg,#F3EFE7_0%,#E7E0D3_55%,#DAD2C3_100%)]" />
      <div className="absolute -right-24 -top-10 h-[130%] w-40 rotate-[28deg] bg-white/45 blur-2xl" />
      <div className="absolute right-40 -top-10 h-[130%] w-24 rotate-[28deg] bg-white/35 blur-2xl" />
      <div className="absolute inset-x-0 bottom-0 h-[24%] border-t border-[#D3CABA] bg-[linear-gradient(180deg,#E3DCCF_0%,#EDE8DF_100%)]" />
      <div className="absolute bottom-[24%] left-[10%] h-[30%] w-[22%] rounded-t-full bg-[linear-gradient(180deg,#E0D6C4_0%,#D2C6B1_100%)] shadow-[inset_0_18px_40px_rgba(92,91,74,0.12)]" />
      <div className="absolute bottom-[21%] left-[6%] h-8 w-[34%] rounded-[50%] bg-[#5C5B4A]/15 blur-md" />
      <div className="absolute bottom-[22%] left-[27%] h-24 w-24 rounded-full bg-[radial-gradient(circle_at_35%_30%,#D7B08C_0%,#B98C66_55%,#8E6645_100%)] shadow-[0_18px_30px_rgba(92,91,74,0.25)]" />
    </div>
  );
}

export function AuthShell({ eyebrow, title, subtitle, children }) {
  const { pathname } = useLocation();
  const onRegister = pathname.startsWith("/register");

  return (
    <div className="min-h-screen bg-white lg:grid lg:grid-cols-[1.1fr_1fr]">
      <aside className="relative hidden min-h-screen overflow-hidden lg:block">
        <Scene />
        <div className="relative flex h-full flex-col px-12 py-10">
          <div className="flex items-center justify-between">
            <Logo />
            <nav className="flex gap-6 text-xs text-ink/70">
              <span>Orders</span>
              <span>Couriers</span>
              <span>Cash on delivery</span>
              <span>Profit</span>
            </nav>
          </div>

          <div className="mt-[9vh] text-center">
            <h2 className="font-display text-7xl font-normal leading-[0.92] tracking-tight text-ink xl:text-8xl">
              Every order,
              <br />
              in balance
            </h2>
            <p className="mt-4 font-display text-3xl italic text-ink/80">
              {"{Made for F-commerce '26}"}
            </p>
          </div>

          <div className="mt-auto flex items-end justify-end">
            <div className="max-w-[15rem] text-right">
              <p className="text-xs leading-relaxed text-ink/80">
                Confirm on Messenger, ship with any courier, and watch the cash come home.
              </p>
              <Link to={onRegister ? "/login" : "/register"}
                className="btn-primary mt-4 w-full">
                {onRegister ? "I already have an account" : "Start for free"}
              </Link>
            </div>
          </div>
        </div>
      </aside>

      <main className="flex min-h-screen items-center justify-center px-6 py-12 lg:px-16">
        <div className="w-full max-w-sm">
          <div className="mb-10 lg:hidden"><Logo /></div>
          {eyebrow && <p className="eyebrow">{eyebrow}</p>}
          <h1 className="mt-2 font-display text-5xl font-normal leading-none tracking-tight">{title}</h1>
          {subtitle && <p className="mt-3 text-sm text-muted">{subtitle}</p>}
          <div className="mt-8">{children}</div>
        </div>
      </main>
    </div>
  );
}
