export type Source = {
  chunk_id: string;
  document_id: string;
  title: string;
  content: string;
  source_location: Record<string, unknown>;
};
export type GeneratedPost = {
  id: string;
  platform: "linkedin" | "facebook";
  language: "en" | "he";
  content: string;
  sources: Source[];
  warnings: string[];
  grounded: boolean;
  metadata: { model: string; brand_version: number; prompt_version: string };
};
export type SavedPost = {
  id: string;
  platform: "linkedin" | "facebook";
  language: "en" | "he";
  content: string;
  status: "Draft";
  version: number;
  sources: Source[];
  generation_run_id: string | null;
  created_at: string;
};
export async function apiRequest<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(url, { cache: "no-store", ...init });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message ?? "api_unavailable");
  return data;
}
export const inputClass =
  "w-full rounded-lg border border-border bg-background px-3 py-2.5 text-start text-sm leading-6 focus-visible:outline-2 focus-visible:outline-primary";
