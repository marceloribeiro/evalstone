import type { Role } from "@/lib/types";

/** Mirrors the API's `Role.rank`: member < admin < owner. */
const RANK: Record<Role, number> = { member: 0, admin: 1, owner: 2 };

export const roleAtLeast = (role: Role | undefined, min: Role) => role !== undefined && RANK[role] >= RANK[min];
/** What the API gates with `require(Role.ADMIN)` / `require_project(Role.ADMIN)`. */
export const isAdmin = (role: Role | undefined) => roleAtLeast(role, "admin");
