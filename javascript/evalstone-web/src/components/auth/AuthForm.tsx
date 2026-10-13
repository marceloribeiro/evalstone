"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { useAuth } from "@/contexts/AuthContext";
import { errorMessage } from "@/lib/api";
import { lastOrganization } from "@/contexts/WorkspaceContext";
import { Brand } from "@/components/layout/Brand";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const { login, register } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password, firstName, lastName);
      const last = lastOrganization();
      router.replace(last ? `/o/${last}` : "/organizations");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <Brand href={null} className="mb-2" />
          <h1 className="font-heading text-base leading-snug font-medium">
            {mode === "login" ? "Sign in" : "Create your account"}
          </h1>
          <CardDescription>
            {mode === "login" ? "The Evalstone center." : "Then create or join an organization."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            {mode === "register" && (
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="first_name">First name</Label>
                  <Input id="first_name" value={firstName} onChange={(e) => setFirstName(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="last_name">Last name</Label>
                  <Input id="last_name" value={lastName} onChange={(e) => setLastName(e.target.value)} />
                </div>
              </div>
            )}
            <div className="space-y-1">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
            <Button type="submit" className="w-full" disabled={busy}>
              {mode === "login" ? "Sign in" : "Create account"}
            </Button>
          </form>
          <p className="mt-4 text-center text-sm text-muted-foreground">
            {mode === "login" ? (
              <>
                New here? <Link href="/register" className="underline">Create an account</Link>
              </>
            ) : (
              <>
                Already have one? <Link href="/login" className="underline">Sign in</Link>
              </>
            )}
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
