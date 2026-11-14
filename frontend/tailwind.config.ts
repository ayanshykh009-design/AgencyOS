import type { Config } from "tailwindcss";

// AgencyOS design tokens (Commercial V1, dark-first).
// Neutral and semantic values are the printed Sheet 1 / Sheet 2A labels:
// neutrals Obsidian..Silver, semantics success/warning/danger/info/AI accent.
// Typography: Satoshi (display) and JetBrains Mono are not bundled in this
// repository (unlicensed); the stacks below fall back per the design spec
// (Satoshi → Inter Display → system UI, mono → DejaVu Sans Mono).
const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        obsidian: "#050505",
        "deep-graphite": "#0B0B0B",
        graphite: "#111111",
        elevated: "#181818",
        line: "#2A2A2A",
        "soft-gray": "#A3A3A3",
        muted: "#737373",
        "off-white": "#F5F5F5",
        silver: "#C7C7C7",
        success: "#22C55E",
        warning: "#F59E0B",
        danger: "#EF4444",
        info: "#3B82F6",
        ai: "#8B5CF6",
      },
      fontFamily: {
        display: [
          "Satoshi",
          "Inter Display",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Cascadia Mono",
          "DejaVu Sans Mono",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
