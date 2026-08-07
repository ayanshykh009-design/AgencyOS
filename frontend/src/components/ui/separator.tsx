// Separator primitive.
import { cn } from "@/lib/utils";

interface SeparatorProps extends React.HTMLAttributes<HTMLHRElement> {}

export function Separator({ className, ...props }: SeparatorProps) {
  return <hr className={cn("border-gray-200", className)} {...props} />;
}
