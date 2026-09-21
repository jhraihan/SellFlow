import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { relative } from "@/lib/format";
import { Alert, EmptyState, PageLoader } from "@/components/ui";

const LEVEL_CLASSES = {
  info: "border-line bg-white",
  warning: "border-amber-300 bg-amber-50",
  critical: "border-red-300 bg-red-50",
};

export default function Notifications() {
  const { storeId } = useAuth();
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["notifications", storeId],
    queryFn: async () => (await api.get("/notifications/")).data,
    enabled: Boolean(storeId),
  });

  const markRead = useMutation({
    mutationFn: () => api.post("/notifications/mark-read/", { all: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      queryClient.invalidateQueries({ queryKey: ["unread"] });
    },
  });

  const items = data?.results || [];

  if (isLoading) return <PageLoader label="Loading alerts" />;
  if (error) return <Alert>Could not load alerts.</Alert>;

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Alerts</h1>
          <p className="text-sm text-muted">Things worth your attention.</p>
        </div>
        {items.some((item) => !item.is_read) && (
          <button
            type="button"
            className="btn-secondary text-sm"
            onClick={() => markRead.mutate()}
          >
            Mark all read
          </button>
        )}
      </div>

      {items.length === 0 ? (
        <EmptyState
          title="Nothing to report"
          description="Low stock, overdue COD and returns will show up here."
        />
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li
              key={item.id}
              className={`rounded-xl border p-3 ${
                LEVEL_CLASSES[item.level] || LEVEL_CLASSES.info
              } ${item.is_read ? "opacity-70" : ""}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium">{item.title}</p>
                  {item.body && (
                    <p className="mt-0.5 text-sm text-muted">{item.body}</p>
                  )}
                </div>
                <span className="shrink-0 text-xs text-muted">
                  {relative(item.created_at)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
