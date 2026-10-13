"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { RequireUser } from "@/components/auth/RequireUser";
import { OrganizationList } from "@/components/organizations/OrganizationList";
import { Brand } from "@/components/layout/Brand";
import { Button } from "@/components/ui/button";

export default function OrganizationsPage() {
  const { logout } = useAuth();
  const router = useRouter();
  return (
    <RequireUser>
      {(user) => (
        <div className="min-h-screen">
          <header className="flex h-14 items-center justify-between border-b px-[30px]">
            <Brand />
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <span>{user.email}</span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  logout();
                  router.replace("/login");
                }}
              >
                Sign out
              </Button>
            </div>
          </header>
          <main className="px-[30px] py-6">
            <OrganizationList />
          </main>
        </div>
      )}
    </RequireUser>
  );
}
