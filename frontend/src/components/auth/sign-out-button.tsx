// Sign-out control for the authenticated app shell.
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { ROUTES } from "@/lib/constants";
import { logout } from "@/services/auth";

export function SignOutButton() {
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    setSigningOut(true);
    await logout();
    router.replace(ROUTES.login);
    router.refresh();
  }

  return (
    <Button type="button" variant="ghost" onClick={handleSignOut} disabled={signingOut}>
      {signingOut ? "Signing out…" : "Sign out"}
    </Button>
  );
}
