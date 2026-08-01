// Generic utility helpers (formatting, guards, class-name merging).
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}
