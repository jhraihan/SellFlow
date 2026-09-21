import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { errorMessage, fieldErrors } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Alert, Field, Spinner } from "@/components/ui";
import { AuthShell } from "./Login";

export default function Register() {
  const { register: signUp } = useAuth();
  const navigate = useNavigate();
  const [failure, setFailure] = useState("");

  const {
    register, handleSubmit, getValues, setError,
    formState: { errors, isSubmitting },
  } = useForm();

  async function onSubmit(values) {
    setFailure("");
    try {
      await signUp(values);
      navigate("/onboarding");
    } catch (error) {
      const fields = fieldErrors(error);
      let matched = false;
      for (const [name, message] of Object.entries(fields)) {
        if (name in values) {
          setError(name, { message });
          matched = true;
        }
      }
      if (!matched) setFailure(errorMessage(error));
    }
  }

  return (
    <AuthShell title="Create your account" subtitle="Free for your first 50 orders a month.">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {failure && <Alert>{failure}</Alert>}

        <Field label="Your name" required error={errors.full_name?.message}>
          <input className="input" autoFocus
            {...register("full_name", { required: "Enter your name." })} />
        </Field>

        <Field label="Email" required error={errors.email?.message}>
          <input type="email" autoComplete="email" className="input"
            {...register("email", { required: "Enter your email." })} />
        </Field>

        <Field label="Phone" error={errors.phone?.message}
          hint="Bangladeshi mobile, e.g. 01712345678">
          <input inputMode="numeric" className="input" {...register("phone")} />
        </Field>

        <Field label="Password" required error={errors.password?.message}
          hint="At least 8 characters.">
          <input type="password" autoComplete="new-password" className="input"
            {...register("password", {
              required: "Choose a password.",
              minLength: { value: 8, message: "At least 8 characters." },
            })} />
        </Field>

        <Field label="Confirm password" required error={errors.password_confirm?.message}>
          <input type="password" autoComplete="new-password" className="input"
            {...register("password_confirm", {
              required: "Repeat your password.",
              validate: (v) => v === getValues("password") || "The passwords do not match.",
            })} />
        </Field>

        <button type="submit" disabled={isSubmitting} className="btn-primary w-full">
          {isSubmitting && <Spinner className="h-4 w-4" />}
          Create account
        </button>

        <p className="text-center text-sm text-muted">
          Already registered?{" "}
          <Link to="/login" className="text-brand-600 hover:underline">Sign in</Link>
        </p>
      </form>
    </AuthShell>
  );
}
