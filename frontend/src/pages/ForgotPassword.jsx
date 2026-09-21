import { useState } from "react";
import { Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { api, errorMessage } from "@/lib/api";
import { Alert, Field, Spinner } from "@/components/ui";
import { AuthShell } from "./Login";

export default function ForgotPassword() {
  const [sent, setSent] = useState(false);
  const [failure, setFailure] = useState("");
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm();

  async function onSubmit(values) {
    setFailure("");
    try {
      await api.post("/auth/password/reset/", values);
      setSent(true);
    } catch (error) {
      setFailure(errorMessage(error));
    }
  }

  return (
    <AuthShell title="Reset your password">
      {sent ? (
        <div className="space-y-4">
          <Alert tone="ok" title="Check your email">
            If an account exists for that address, we have sent a reset link.
            It expires in one hour.
          </Alert>
          <Link to="/login" className="btn-secondary w-full">Back to sign in</Link>
        </div>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          {failure && <Alert>{failure}</Alert>}
          <Field label="Email" required error={errors.email?.message}>
            <input type="email" autoFocus className="input"
              {...register("email", { required: "Enter your email." })} />
          </Field>
          <button type="submit" disabled={isSubmitting} className="btn-primary w-full">
            {isSubmitting && <Spinner className="h-4 w-4" />}
            Send reset link
          </button>
          <p className="text-center text-sm">
            <Link to="/login" className="text-brand-600 hover:underline">Back to sign in</Link>
          </p>
        </form>
      )}
    </AuthShell>
  );
}
