import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { api, errorMessage, fieldErrors } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Alert, Field, Spinner } from "@/components/ui";
import { AuthShell } from "./Login";

const BUSINESS_TYPES = [
  ["fashion", "Fashion & Clothing"],
  ["electronics", "Electronics & Gadgets"],
  ["beauty", "Beauty & Cosmetics"],
  ["food", "Food & Grocery"],
  ["home", "Home & Living"],
  ["baby", "Baby & Kids"],
  ["other", "Other"],
];

export default function Onboarding() {
  const navigate = useNavigate();
  const { setStores } = useAuth();
  const [failure, setFailure] = useState("");

  const { register, handleSubmit, setError, formState: { errors, isSubmitting } } =
    useForm({ defaultValues: { business_type: "fashion", order_prefix: "ORD" } });

  async function onSubmit(values) {
    setFailure("");
    try {
      await api.post("/stores/", values);
      const { data } = await api.get("/auth/me/");
      setStores(data.stores || []);
      navigate("/dashboard");
    } catch (error) {
      const fields = fieldErrors(error);
      let matched = false;
      for (const [name, message] of Object.entries(fields)) {
        if (name in values) { setError(name, { message }); matched = true; }
      }
      if (!matched) setFailure(errorMessage(error));
    }
  }

  return (
    <AuthShell eyebrow="Almost there" title="Set up your store" subtitle="You can change any of this later.">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {failure && <Alert>{failure}</Alert>}

        <Field label="Store name" required error={errors.name?.message}>
          <input className="input" autoFocus
            {...register("name", { required: "Give your store a name." })} />
        </Field>

        <Field label="What do you sell?" error={errors.business_type?.message}>
          <select className="input" {...register("business_type")}>
            {BUSINESS_TYPES.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </Field>

        <Field label="District" error={errors.district?.message}
          hint="Used to work out delivery charges.">
          <input className="input" {...register("district")} />
        </Field>

        <Field label="Contact phone" error={errors.contact_phone?.message}>
          <input inputMode="numeric" className="input" {...register("contact_phone")} />
        </Field>

        <Field label="Order number prefix" error={errors.order_prefix?.message}
          hint="Orders will look like RF-1001.">
          <input className="input uppercase" maxLength={8} {...register("order_prefix")} />
        </Field>

        <button type="submit" disabled={isSubmitting} className="btn-primary w-full">
          {isSubmitting && <Spinner className="h-4 w-4" />}
          Create store
        </button>
      </form>
    </AuthShell>
  );
}
