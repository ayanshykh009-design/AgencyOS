// Permission guard component for client-side permission checking.
"use client";

import { useAuth } from "@/hooks/use-auth";
import { Permission } from "@/lib/constants";
import { can } from "@/lib/permissions";

interface PermissionGuardProps {
  permission: Permission;
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

export function PermissionGuard({ permission, children, fallback = null }: PermissionGuardProps) {
  const session = useAuth();

  const allowed = !!session && can(session.user.role, permission);

  if (!allowed) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
}
