// Flat ESLint config for Next.js (eslint-config-next >= 16 ships flat configs
// natively; the legacy FlatCompat shim is no longer compatible).
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import prettier from "eslint-config-prettier";

const eslintConfig = [
  ...nextCoreWebVitals,
  prettier,
  {
    ignores: [".next/**", "node_modules/**", "out/**", "coverage/**", "next-env.d.ts"],
  },
];

export default eslintConfig;
