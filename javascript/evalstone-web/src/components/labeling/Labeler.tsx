"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader } from "@/components/layout/PageHeader";
import { LoadError } from "@/components/common/LoadError";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLoader } from "@/hooks/useLoader";
import { api, ApiError, errorMessage } from "@/lib/api";
import { brief } from "@/lib/format";
import { isBinary } from "@/lib/labeling";
import type { ComparePayload, GradePayload, LabelQueue, LabelTask, QueueProgress, VerifyPayload } from "@/lib/types";

type Choice = { grade?: number; passed?: boolean; winner?: "a" | "b" | "tie" };

/**
 * The labeling screen: claims the next task (`POST …/next`, one claim per `round`), shows it for its
 * kind, and takes the verdict from the keyboard — digits (grade), P/F (pass/fail), A/B/T (compare),
 * N = notes, S = skip, Enter = submit — then claims the next one. Null from `next` means the queue
 * is done. The verdict panel is keyed by the task, so its choice/notes start fresh for each one.
 */
export function Labeler({ queueId }: { queueId: string }) {
  const { organization, project } = useWorkspace();
  const queue = useLoader(() => api<LabelQueue>(`/projects/${project!.id}/label-queues/${queueId}`), [project?.id, queueId]);
  const progress = useLoader(() => api<QueueProgress>(`/projects/${project!.id}/label-queues/${queueId}/progress`), [project?.id, queueId]);
  const [task, setTask] = useState<LabelTask | null | undefined>(undefined); // undefined = claiming, null = nothing left
  const [claimError, setClaimError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const projectId = project?.id;
  const claimedFor = useRef<string | null>(null);
  const reloadProgress = progress.reload;
  const taskRef = useRef<HTMLDivElement>(null);
  // each new task takes focus: hotkeys have a non-interactive home even after a mouse click on a
  // button of the previous task, and screen readers announce the new sample
  useEffect(() => {
    if (task) taskRef.current?.focus();
  }, [task]);

  // claiming is a write (POST …/next), so it is an explicit action: once on mount per queue, then
  // after every answer / skip — never as a by-product of a render or a loader retry
  const claimNext = useCallback(() => {
    if (!projectId) return;
    setTask(undefined);
    setClaimError(null);
    api<LabelTask | null>(`/projects/${projectId}/label-queues/${queueId}/next`, { method: "POST" })
      .then((t) => setTask(t))
      .catch((err) => setClaimError(err));
  }, [projectId, queueId]);
  useEffect(() => {
    const key = `${projectId}:${queueId}`;
    if (!projectId || claimedFor.current === key) return; // StrictMode double-mount: one claim
    claimedFor.current = key;
    claimNext();
  }, [projectId, queueId, claimNext]);

  const advance = useCallback(() => {
    reloadProgress();
    claimNext();
  }, [reloadProgress, claimNext]);

  const submit = useCallback(
    async (taskId: string, choice: Choice, notes: string) => {
      if (!projectId) return;
      setBusy(true);
      try {
        await api(`/projects/${projectId}/label-queues/${queueId}/tasks/${taskId}/answer`, { method: "POST", body: { ...choice, notes } });
        advance();
      } catch (err) {
        toast.error(errorMessage(err));
        if (err instanceof ApiError && err.status === 409) advance(); // claimed elsewhere / closed: move on
      } finally {
        setBusy(false);
      }
    },
    [projectId, queueId, advance],
  );
  const skip = useCallback(
    async (taskId: string, reason: string) => {
      if (!projectId) return;
      setBusy(true);
      try {
        await api(`/projects/${projectId}/label-queues/${queueId}/tasks/${taskId}/skip`, { method: "POST", body: { reason } });
        advance();
      } catch (err) {
        toast.error(errorMessage(err));
        if (err instanceof ApiError && err.status === 409) advance(); // same as answer: do not get stuck on it
      } finally {
        setBusy(false);
      }
    },
    [projectId, queueId, advance],
  );

  if (!organization || !project) return null;
  const base = `/o/${organization.id}/p/${project.id}`;
  const q = queue.data;
  const crumbs = [
    { label: "Home", href: "/organizations" },
    { label: organization.name, href: `/o/${organization.id}` },
    { label: project.name, href: base },
    { label: "Labeling", href: `${base}/labeling` },
    { label: q?.name ?? "…", href: `${base}/labeling/${queueId}` },
    { label: "Label" },
  ];
  if (!q) {
    if (queue.loading) return <Skeleton className="h-40 w-full" data-testid="loading" />;
    return (
      <div>
        <PageHeader title="Label" crumbs={crumbs} />
        <LoadError what="this queue" error={queue.error} retry={queue.reload} />
      </div>
    );
  }
  const p = progress.data;
  const counter = p ? `${p.done + p.skipped} of ${p.total} done` : "";

  return (
    <div>
      <PageHeader
        title={q.name}
        description={q.instructions || "No instructions given."}
        crumbs={crumbs}
        actions={
          <span className="text-sm text-muted-foreground" data-testid="counter">
            {counter}
          </span>
        }
      />
      {claimError ? (
        <LoadError what="the next task" error={claimError} retry={claimNext} />
      ) : task === undefined ? (
        <Skeleton className="h-40 w-full" data-testid="claiming" />
      ) : task === null ? (
        <Card>
          <CardContent className="space-y-2 py-6" data-testid="queue-done">
            <p className="font-medium">Nothing left to label.</p>
            <p className="text-sm text-muted-foreground">Every task is done, skipped, or claimed by someone else.</p>
            <Link href={`${base}/labeling/${q.id}`} className="text-sm underline-offset-4 hover:underline">
              Back to the queue
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4 outline-none" data-testid="task" data-task-id={task.id} ref={taskRef} tabIndex={-1} aria-label={`Task ${task.position}: sample ${task.sample_key}`}>
          <p className="text-sm text-muted-foreground">
            Sample <code>{task.sample_key}</code> · task #{task.position}
          </p>
          {q.kind === "grade" && <GradeCard payload={task.payload as GradePayload} />}
          {q.kind === "compare" && <CompareCard payload={task.payload as ComparePayload} />}
          {q.kind === "verify" && <VerifyCard payload={task.payload as VerifyPayload} />}
          <VerdictPanel key={task.id} queue={q} busy={busy} onSubmit={(c, n) => submit(task.id, c, n)} onSkip={(n) => skip(task.id, n)} />
        </div>
      )}
    </div>
  );
}

const SKIP_ARM_MS = 4000;

/** The verdict controls for one task: owns the choice and notes, listens to the keyboard. */
function VerdictPanel({ queue: q, busy, onSubmit, onSkip }: { queue: LabelQueue; busy: boolean; onSubmit: (choice: Choice, notes: string) => void; onSkip: (notes: string) => void }) {
  const [choice, setChoice] = useState<Choice>({});
  const [notes, setNotes] = useState("");
  const [skipArmed, setSkipArmed] = useState(false);
  const notesRef = useRef<HTMLTextAreaElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const binary = isBinary(q.kind, q.scale);
  const canSubmit = !busy && (q.kind === "compare" ? !!choice.winner : binary ? choice.passed !== undefined : choice.grade !== undefined);
  const submit = useCallback(() => {
    if (canSubmit) onSubmit(choice, notes);
  }, [canSubmit, onSubmit, choice, notes]);
  // a skip is terminal (no un-skip on the API), so it takes two presses: the first arms for a few seconds
  const skip = useCallback(() => {
    if (busy) return;
    if (skipArmed) onSkip(notes);
    else setSkipArmed(true);
  }, [busy, skipArmed, onSkip, notes]);
  useEffect(() => {
    if (!skipArmed) return;
    const t = setTimeout(() => setSkipArmed(false), SKIP_ARM_MS);
    return () => clearTimeout(t);
  }, [skipArmed]);

  // keyboard: only when nothing interactive has focus (a focused button gets its own click on Enter);
  // ignored while typing in the notes box (Esc leaves it; Cmd/Ctrl+Enter submits from it)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const active = document.activeElement;
      if (active === notesRef.current) {
        if (e.key === "Escape") notesRef.current?.blur();
        else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
        return;
      }
      if (active && active !== document.body && active.matches("button, a, input, select, textarea, [contenteditable]")) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "enter") return submit();
      if (k === "s") return skip();
      if (k !== "s" && skipArmed) setSkipArmed(false); // any other key disarms
      if (k === "n") {
        e.preventDefault();
        return notesRef.current?.focus();
      }
      if (q.kind === "compare") {
        if (k === "a" || k === "b" || k === "t") setChoice({ winner: k === "t" ? "tie" : k });
      } else if (binary) {
        if (k === "p") setChoice({ passed: true });
        if (k === "f") setChoice({ passed: false });
      } else {
        const n = k === "0" ? 10 : Number(k);
        if (Number.isInteger(n) && n >= 1 && n <= q.scale) setChoice({ grade: n });
      }
    };
    window.addEventListener("keydown", onKey);
    panelRef.current?.setAttribute("data-hotkeys", "ready"); // set from the same effect: "the listener is attached"
    return () => window.removeEventListener("keydown", onKey);
  }, [q.kind, q.scale, binary, submit, skip, skipArmed]);

  return (
    <Card ref={panelRef} data-testid="verdict">
      <CardHeader>
        <CardTitle>Your verdict</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Verdict">
          {q.kind === "compare" ? (
            (["a", "b", "tie"] as const).map((w) => (
              <Button key={w} variant={choice.winner === w ? "default" : "outline"} aria-pressed={choice.winner === w} onClick={() => setChoice({ winner: w })}>
                {w === "tie" ? "Tie (T)" : `${w.toUpperCase()} is better (${w.toUpperCase()})`}
              </Button>
            ))
          ) : binary ? (
            <>
              <Button variant={choice.passed === true ? "default" : "outline"} aria-pressed={choice.passed === true} onClick={() => setChoice({ passed: true })}>
                {q.kind === "verify" ? "Expected is correct (P)" : "Pass (P)"}
              </Button>
              <Button variant={choice.passed === false ? "destructive" : "outline"} aria-pressed={choice.passed === false} onClick={() => setChoice({ passed: false })}>
                {q.kind === "verify" ? "Expected is wrong (F)" : "Fail (F)"}
              </Button>
            </>
          ) : (
            Array.from({ length: q.scale }, (_, i) => i + 1).map((n) => (
              <Button key={n} variant={choice.grade === n ? "default" : "outline"} aria-pressed={choice.grade === n} aria-label={`Grade ${n}`} onClick={() => setChoice({ grade: n })}>
                {n === 10 ? "10 (0)" : n}
              </Button>
            ))
          )}
        </div>
        <Textarea ref={notesRef} aria-label="Notes" placeholder="Notes (N) — optional; Esc to leave, ⌘/Ctrl+Enter to submit" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
        <div className="flex items-center gap-2">
          <Button disabled={!canSubmit} onClick={submit}>
            Submit (Enter)
          </Button>
          <Button variant={skipArmed ? "destructive" : "outline"} disabled={busy} onClick={skip} aria-pressed={skipArmed}>
            {skipArmed ? "Press again to skip (S)" : "Skip (S)"}
          </Button>
          <span className="ml-auto text-xs text-muted-foreground">
            Keys: {q.kind === "compare" ? "A · B · T" : binary ? "P · F" : `1–${q.scale}`} · N notes · S skip · Enter submit
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

function Field({ label, value, mono = true }: { label: string; value: unknown; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className={`whitespace-pre-wrap break-words text-sm ${mono ? "font-mono" : ""}`}>{brief(value, 4000) || <span className="text-muted-foreground">—</span>}</dd>
    </div>
  );
}

function GradeCard({ payload }: { payload: GradePayload }) {
  return (
    <Card>
      <CardContent className="grid gap-4 py-4 md:grid-cols-2">
        <dl className="space-y-3">
          <Field label="Input" value={payload.input} />
          <Field label="Expected" value={payload.expected} />
        </dl>
        <dl className="space-y-3">
          <Field label="Output" value={payload.output.value} />
          <div>
            <dt className="text-xs font-medium text-muted-foreground">Machine verdict ({payload.check_key})</dt>
            <dd className="text-sm">
              <Badge variant={payload.machine.passed ? "default" : "destructive"}>{payload.machine.passed ? "pass" : "fail"}</Badge> {payload.machine.score.toFixed(2)}
              {payload.machine.reason && <span className="ml-2 text-muted-foreground">{payload.machine.reason}</span>}
            </dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}

function CompareCard({ payload }: { payload: ComparePayload }) {
  return (
    <Card>
      <CardContent className="space-y-4 py-4">
        <dl className="grid gap-3 md:grid-cols-2">
          <Field label="Input" value={payload.input} />
          <Field label="Expected" value={payload.expected} />
        </dl>
        <div className="grid gap-3 md:grid-cols-2">
          <dl className="rounded-md border p-3" data-testid="output-a">
            <Field label="A" value={payload.a.output.value} />
          </dl>
          <dl className="rounded-md border p-3" data-testid="output-b">
            <Field label="B" value={payload.b.output.value} />
          </dl>
        </div>
      </CardContent>
    </Card>
  );
}

function VerifyCard({ payload }: { payload: VerifyPayload }) {
  return (
    <Card>
      <CardContent className="py-4">
        <dl className="grid gap-3 md:grid-cols-2">
          <Field label="Input" value={payload.input} />
          <Field label="Expected (is this right?)" value={payload.expected} />
        </dl>
      </CardContent>
    </Card>
  );
}
