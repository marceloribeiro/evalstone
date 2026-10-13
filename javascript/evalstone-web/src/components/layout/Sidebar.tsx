"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Activity, Bell, BookOpen, ChevronsLeft, ChevronsRight, Database, Home, ListChecks, LogOut, Play, Scale, Settings, Tags } from "lucide-react";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/contexts/AuthContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLocalStorageFlag } from "@/hooks/useLocalStorageFlag";
import { Brand } from "@/components/layout/Brand";

const KEY = "evalstone.sidebar.collapsed";

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { logout, user } = useAuth();
  const { organization, project, projects } = useWorkspace();
  const [collapsed, setCollapsed] = useLocalStorageFlag(KEY);
  if (!organization) return null;

  const orgBase = `/o/${organization.id}`;
  const base = project ? `${orgBase}/p/${project.id}` : orgBase;
  const items = project
    ? [
        { href: base, label: "Overview", icon: Home, exact: true },
        { href: `${base}/runs`, label: "Runs", icon: Play },
        { href: `${base}/datasets`, label: "Datasets", icon: Database },
        { href: `${base}/labeling`, label: "Labeling", icon: ListChecks },
        { href: `${base}/judges`, label: "Judges", icon: Scale },
        { href: `${base}/monitors`, label: "Monitors", icon: Activity },
        { href: `${base}/alerts`, label: "Alerts", icon: Bell },
        { href: `${base}/settings`, label: "Settings", icon: Settings },
      ]
    : [
        { href: orgBase, label: "Projects", icon: Home, exact: true },
        { href: `${orgBase}/checks`, label: "Check catalog", icon: Tags },
        { href: `${orgBase}/providers`, label: "Providers", icon: BookOpen },
        { href: `${orgBase}/members`, label: "Members", icon: Settings },
      ];

  const switchProject = (id: string | null) => {
    if (!id) return;
    router.push(id === "__org__" ? orgBase : `${orgBase}/p/${id}`);
  };

  return (
    <aside
      data-testid="sidebar"
      className={cn(
        "sticky top-0 flex h-screen shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width]",
        collapsed ? "w-14" : "w-60",
      )}
    >
      <div className={cn("flex h-14 items-center border-b border-sidebar-border", collapsed ? "justify-center" : "px-4")}>
        <Brand mark={collapsed} />
      </div>
      {!collapsed && (
        <div className="border-b border-sidebar-border p-3">
          <p className="truncate text-xs text-muted-foreground" title={organization.name}>
            {organization.name}
          </p>
          <Select
            value={project?.id ?? "__org__"}
            onValueChange={switchProject}
            items={{ __org__: "Organization home", ...Object.fromEntries(projects.map((p) => [p.id, p.name])) }}
          >
            <SelectTrigger aria-label="Project" className="mt-1 w-full">
              <SelectValue placeholder="Project" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__org__">Organization home</SelectItem>
              {projects.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
      <nav className="flex-1 space-y-1 p-2" aria-label="Main">
        {items.map(({ href, label, icon: Icon, exact }) => {
          const active = exact ? pathname === href : pathname === href || pathname.startsWith(href + "/");
          const link = (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors hover:bg-sidebar-accent",
                active && "bg-sidebar-accent font-medium",
                collapsed && "justify-center px-0",
              )}
            >
              <Icon className="size-4 shrink-0" aria-hidden />
              {!collapsed && <span>{label}</span>}
              {collapsed && <span className="sr-only">{label}</span>}
            </Link>
          );
          return collapsed ? (
            <Tooltip key={href}>
              <TooltipTrigger render={link} />
              <TooltipContent side="right">{label}</TooltipContent>
            </Tooltip>
          ) : (
            link
          );
        })}
      </nav>
      <div className="space-y-1 border-t border-sidebar-border p-2">
        {!collapsed && user && (
          <p className="truncate px-3 text-xs text-muted-foreground" title={user.email}>
            {user.email}
          </p>
        )}
        <button
          type="button"
          onClick={() => {
            logout();
            router.replace("/login");
          }}
          className={cn("flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm hover:bg-sidebar-accent", collapsed && "justify-center px-0")}
        >
          <LogOut className="size-4" aria-hidden />
          {collapsed ? <span className="sr-only">Sign out</span> : <span>Sign out</span>}
        </button>
        <button
          type="button"
          onClick={() => setCollapsed(!collapsed)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn("flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm hover:bg-sidebar-accent", collapsed && "justify-center px-0")}
        >
          {collapsed ? <ChevronsRight className="size-4" aria-hidden /> : <ChevronsLeft className="size-4" aria-hidden />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
