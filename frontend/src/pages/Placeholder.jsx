import { EmptyState } from "@/components/ui";

export default function Placeholder({ title, description }) {
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">{title}</h1>
      <EmptyState
        title="Not built yet"
        description={description || "This screen is next on the list."}
      />
    </div>
  );
}
