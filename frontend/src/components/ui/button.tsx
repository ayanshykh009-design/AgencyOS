// Reusable UI primitives (buttons, inputs, cards, modals).
// Build on Tailwind; keep them presentational and props-driven
// (no data fetching, no business logic).

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "solid" | "ghost" | "outline" | "danger";
}

const VARIANTS: Record<NonNullable<ButtonProps["variant"]>, string> = {
  solid: "bg-black text-white hover:bg-gray-800",
  ghost: "bg-transparent text-gray-600 hover:bg-gray-100",
  outline: "border border-gray-300 bg-white text-gray-700 hover:bg-gray-50",
  danger: "bg-red-600 text-white hover:bg-red-700",
};

export function Button({ variant = "solid", className, ...props }: ButtonProps) {
  return (
    <button
      className={`rounded-md px-4 py-2 text-sm font-medium disabled:opacity-50 ${VARIANTS[variant]} ${className ?? ""}`}
      {...props}
    />
  );
}
