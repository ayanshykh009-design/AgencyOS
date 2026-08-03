// Empty state placeholder for lists with no content.
interface EmptyStateProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed bg-gray-50 px-6 py-10 text-center">
      <p className="text-sm font-medium text-gray-700">{title}</p>
      {description ? <p className="max-w-sm text-sm text-gray-500">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
