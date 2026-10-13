"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Organization, Project } from "@/lib/types";

/** The org and project the URL points at, resolved once per id (what every page under /o/… needs). */
type Workspace = {
  organization: Organization | null;
  project: Project | null;
  projects: Project[];
  loading: boolean;
  reloadProjects: () => void;
};

const Ctx = createContext<Workspace | null>(null);
const LAST_ORG = "evalstone.last-org";

export function rememberOrganization(id: string) {
  try {
    window.localStorage.setItem(LAST_ORG, id);
  } catch {
    /* ignore */
  }
}

export function lastOrganization(): string | null {
  try {
    return window.localStorage.getItem(LAST_ORG);
  } catch {
    return null;
  }
}

export function WorkspaceProvider({
  organizationId,
  projectId,
  children,
}: {
  organizationId: string;
  projectId?: string;
  children: React.ReactNode;
}) {
  // `loaded.key` says which (org, tick) the data belongs to; loading = it is not the current one.
  type Loaded = { key: string; organization: Organization | null; projects: Project[] };
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [tick, setTick] = useState(0);
  const key = `${organizationId}:${tick}`;

  useEffect(() => {
    let alive = true;
    Promise.all([api<Organization>(`/organizations/${organizationId}`), api<Project[]>(`/organizations/${organizationId}/projects`)])
      .then(([org, ps]) => {
        if (!alive) return;
        rememberOrganization(org.id);
        setLoaded({ key, organization: org, projects: ps });
      })
      .catch(() => {
        if (alive) setLoaded({ key, organization: null, projects: [] });
      });
    return () => {
      alive = false;
    };
  }, [organizationId, key]);

  const current = loaded && loaded.key === key ? loaded : null;
  const loading = current === null;
  const organization = current?.organization ?? null;
  const projects = useMemo(() => current?.projects ?? [], [current]);
  const reloadProjects = useCallback(() => setTick((t) => t + 1), []);
  const project = useMemo(() => projects.find((p) => p.id === projectId) ?? null, [projects, projectId]);
  const value = useMemo<Workspace>(
    () => ({ organization, project, projects, loading, reloadProjects }),
    [organization, project, projects, loading, reloadProjects],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWorkspace(): Workspace {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useWorkspace outside WorkspaceProvider");
  return ctx;
}
