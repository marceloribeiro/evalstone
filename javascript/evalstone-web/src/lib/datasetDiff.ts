import { api } from "@/lib/api";
import type { Page, Sample } from "@/lib/types";

export type SampleDiff = {
  added: Sample[];
  removed: Sample[];
  /** same sample key, different content hash (input / expected / tags — metadata is not part of the hash) */
  changed: { key: string; before: Sample; after: Sample }[];
  unchanged: number;
};

/** Version B relative to version A, matched by the library's sample id (`sample_key`). */
export function diffSamples(a: Sample[], b: Sample[]): SampleDiff {
  const byKeyA = new Map(a.map((s) => [s.sample_key, s]));
  const byKeyB = new Map(b.map((s) => [s.sample_key, s]));
  const out: SampleDiff = { added: [], removed: [], changed: [], unchanged: 0 };
  for (const s of b) {
    const before = byKeyA.get(s.sample_key);
    if (!before) out.added.push(s);
    else if (before.content_hash !== s.content_hash) out.changed.push({ key: s.sample_key, before, after: s });
    else out.unchanged += 1;
  }
  for (const s of a) if (!byKeyB.has(s.sample_key)) out.removed.push(s);
  return out;
}

const PAGE = 1000; // the API's max page

/** Every sample of a version, in position order (a version holds at most 5,000). */
export async function fetchAllSamples(projectId: string, datasetId: string, version: number): Promise<Sample[]> {
  const all: Sample[] = [];
  for (let offset = 0; ; offset += PAGE) {
    const page = await api<Page<Sample>>(`/projects/${projectId}/datasets/${datasetId}/versions/${version}/samples`, { query: { offset, limit: PAGE } });
    all.push(...page.items);
    if (all.length >= page.total || page.items.length === 0) return all;
  }
}
