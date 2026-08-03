// Spinner primitive for loading states.
export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-gray-500" role="status" aria-live="polite">
      <span
        className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-gray-900"
        aria-hidden
      />
      <span>{label}</span>
    </div>
  );
}
