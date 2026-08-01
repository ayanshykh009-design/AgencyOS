// Route-level loading state shown during streaming/server rendering.
export default function Loading() {
  return (
    <div className="flex min-h-screen items-center justify-center" aria-busy="true">
      <p className="text-sm text-muted-foreground">Loading…</p>
    </div>
  );
}
