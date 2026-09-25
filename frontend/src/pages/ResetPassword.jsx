import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { api, errorMessage, fieldErrors } from "@/lib/api";
import { Alert, Field, Spinner } from "@/components/ui";
import { AuthShell } from "./Login";

export default function ResetPassword() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [failure, setFailure] = useState("");
  const { register, handleSubmit, getValues, setError, formState: { errors, isSubmitting } } =
    useForm();

  async function onSubmit(values) {
    setFailure("");
    try {
      await api.post("/auth/password/reset/confirm/", {
        token, new_password: values.new_password,
      });
      navigate("/login", { replace: true });
    } catch (error) {
      const fields = fieldErrors(error);
      if (fields.new_password) setError("new_password", { message: fields.new_password });
      else setFailure(errorMessage(error));
    }
  }

  return (
    <AuthShell eyebrow="Account" title="Choose a new password">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {failure && (
          <Alert>
            {failure}{" "}
            <Link to="/forgot-password" className="underline">Request a new link</Link>
          </Alert>
        )}

        <Field label="New password" required error={errors.new_password?.message}
          hint="At least 8 characters.">
          <input type="password" autoFocus autoComplete="new-password" className="input"
            {...register("new_password", {
              required: "Choose a password.",
              minLength: { value: 8, message: "At least 8 characters." },
            })} />
        </Field>

        <Field label="Confirm password" required error={errors.confirm?.message}>
          <input type="password" autoComplete="new-password" className="input"
            {...register("confirm", {
              required: "Repeat your password.",
              validate: (v) => v === getValues("new_password") || "The passwords do not match.",
            })} />
        </Field>

        <button type="submit" disabled={isSubmitting} className="btn-primary w-full">
          {isSubmitting && <Spinner className="h-4 w-4" />}
          Set new password
        </button>
      </form>
    </AuthShell>
  );
}
