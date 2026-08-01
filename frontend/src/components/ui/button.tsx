// Reusable UI primitives (buttons, inputs, cards, modals).
// Build on Tailwind; keep them presentational and props-driven
// (no data fetching, no business logic).

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {}

export function Button({ className, ...props }: ButtonProps) {
  return (
    <button
      className={`rounded-md bg-black px-4 py-2 text-sm font-medium text-white disabled:opacity-50 ${className ?? ""}`}
      {...props}
    />
  );
}
