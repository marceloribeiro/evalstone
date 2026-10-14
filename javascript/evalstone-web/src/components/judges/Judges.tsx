"use client";

import { PageHeader } from "@/components/layout/PageHeader";
import { JudgeSettingsCard } from "@/components/judges/JudgeSettingsCard";
import { CalibrationsCard } from "@/components/judges/CalibrationsCard";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLoader } from "@/hooks/useLoader";
import { api } from "@/lib/api";
import type { JudgeSettings, Provider } from "@/lib/types";

/** Judges for this project: which models they run on, which versions were seen, how they agree with humans. */
export function Judges() {
  const { organization, project } = useWorkspace();
  const providers = useLoader(() => api<Provider[]>(`/organizations/${organization!.id}/providers`), [organization?.id]);
  const settings = useLoader(() => api<JudgeSettings>(`/projects/${project!.id}/judge-settings`), [project?.id]);
  if (!organization || !project) return null;
  const base = `/o/${organization.id}/p/${project.id}`;
  return (
    <div>
      <PageHeader
        title="Judges"
        description="LLM judges score outputs the way the check prompts ask; humans label a sample; a calibration says how much to trust each judge version."
        crumbs={[{ label: "Home", href: "/organizations" }, { label: organization.name, href: `/o/${organization.id}` }, { label: project.name, href: base }, { label: "Judges" }]}
      />
      <div className="space-y-6">
        <JudgeSettingsCard organizationId={organization.id} projectId={project.id} providers={providers} settings={settings} />
        <CalibrationsCard projectId={project.id} settings={settings} />
      </div>
    </div>
  );
}
