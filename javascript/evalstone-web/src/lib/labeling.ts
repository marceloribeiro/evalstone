import type { QueueKind } from "@/lib/types";

export const KIND_LABEL: Record<QueueKind, string> = { grade: "Grade outputs", compare: "A/B compare", verify: "Verify dataset" };
/** Verify queues and 2-point grade queues take a pass/fail verdict; the others a 1..scale grade. */
export const isBinary = (kind: QueueKind, scale: number) => kind === "verify" || scale === 2;
