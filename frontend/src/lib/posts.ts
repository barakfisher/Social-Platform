export type Source = {
  chunk_id: string;
  document_id: string;
  title: string;
  content: string;
  source_location: Record<string, unknown>;
};
export type Finding = {
  code: string;
  sentence: string | null;
  claim: string | null;
};
export type KnowledgeLevel = "general" | "knowledge_base";
// Inputs stored before the knowledge level existed were written from the Knowledge Base only.
export function knowledgeLevel(preferences?: {
  knowledge_level?: KnowledgeLevel;
}): KnowledgeLevel {
  return preferences?.knowledge_level ?? "knowledge_base";
}
export type KnowledgeShare = {
  sourced_claims: number;
  general_claims: number;
  unsupported_claims: number;
  // Sourced claims out of all non-creative ones; null when there are none.
  percent: number | null;
  general_sentences: number;
};
export type Review = {
  // "not_requested": a new draft before "Check sources"; findings hold only the free
  // checks (unlisted contact details, wrong language). "blocked": saved drafts only; the
  // text is kept but must not be published.
  status: "not_requested" | "checked" | "unchecked" | "blocked";
  findings: Finding[];
  // Unchecked only: why the check did not complete, and whether retrying can help.
  reason: string | null;
  retryable: boolean;
  checked_at?: string;
  // Saved drafts only: the draft version the review applies to; null means an edited copy.
  checked_version?: number | null;
  // Checked reviews from source-review-v9 on.
  knowledge_share?: KnowledgeShare;
};
export type GeneratedPost = {
  id: string;
  platform: "linkedin" | "facebook";
  language: "en" | "he";
  content: string;
  sources: Source[];
  offer_details: string;
  warnings: string[];
  grounded: boolean;
  metadata: {
    model: string;
    brand_version: number;
    prompt_version: string;
    grounding_review: Review;
    preferences: { review_model: string; knowledge_level?: KnowledgeLevel };
  };
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
  generation_settings: {
    grounding_review?: Review;
    preferences?: { review_model?: string; knowledge_level?: KnowledgeLevel };
  };
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
