export type DraftStatus =
  | "queued"
  | "extracting_transcript"
  | "translating"
  | "generating_content"
  | "verifying"
  | "creating_image"
  | "draft"
  | "needs_review"
  | "transcript_unavailable"
  | "failed";

export const STATUS_LABELS: Record<DraftStatus, string> = {
  queued: "Queued",
  extracting_transcript: "Finding video",
  translating: "Translating",
  generating_content: "Generating content",
  verifying: "Verifying",
  creating_image: "Creating image",
  draft: "Draft",
  needs_review: "Needs review",
  transcript_unavailable: "Transcript unavailable",
  failed: "Failed",
};

export const IN_PROGRESS_STATUSES: DraftStatus[] = ["queued", "extracting_transcript", "translating", "generating_content", "verifying", "creating_image"];

export interface Channel {
  id: number;
  youtube_channel_id: string;
  name: string;
  handle: string | null;
  url: string;
  is_default: boolean;
}

export interface ChannelCandidate {
  name: string;
  handle: string | null;
  url: string;
}

export interface ResolvedChannel {
  channel_id: string;
  name: string;
  handle: string | null;
  url: string;
  already_saved: boolean;
}

export interface VerificationFinding {
  issue_type: string;
  description: string;
  evidence_segment_ids: string[];
  severity: "low" | "medium" | "high";
}

export interface DraftVideo {
  id: number;
  title: string;
  thumbnail_url: string | null;
  published_at: string | null;
  source_url: string;
  channel_name: string | null;
}

export interface PublishInfo {
  status: "publishing" | "published" | "uncertain" | "failed";
  post_url: string | null;
  published_at: string | null;
  error: string | null;
}

export interface Draft {
  id: number;
  card_date: string;
  status: DraftStatus;
  last_error: string | null;
  video: DraftVideo | null;
  source_language: string | null;
  translated_text: string | null;
  summary_text: string | null;
  key_points: { text: string; segment_ids: string[] }[] | null;
  post_text: string | null;
  hashtags: string[] | null;
  verification: VerificationFinding[] | null;
  image_headline: string | null;
  image_takeaways: string[] | null;
  image_url: string | null;
  image_outdated: boolean;
  revision_count: number;
  created_at: string;
  updated_at: string;
  publish: PublishInfo | null;
}

export interface GeminiSettingsStatus {
  configured: boolean;
  source: "ui" | "env" | null;
  masked: string | null;
  model: string;
  supported_models: string[];
}

export interface LlmSettingsStatus {
  provider: "gemini" | "ollama" | "nvidia";
  ollama_model: string;
  ollama_base_url: string;
  ollama_supported_models: string[];
}

export interface NvidiaSettingsStatus {
  configured: boolean;
  source: "ui" | "env" | null;
  masked: string | null;
  model: string;
  supported_models: string[];
}

export interface LinkedInSettingsStatus {
  app_configured: boolean;
  app_source: "ui" | "env" | null;
  app_masked: string | null;
  redirect_uri: string;
  connection: {
    connected: boolean;
    account_name?: string;
    expired?: boolean;
    expires_at?: string | null;
  };
}

export interface BrandSettings {
  brand_name: string;
  image_footer: string;
  brand_color_primary: string;
  brand_color_secondary: string;
  brand_color_text: string;
  image_template: "classic" | "minimal";
  content_tone: "professional" | "conversational" | "enthusiastic";
  output_language: string;
  timezone: string;
  default_channel_id: number | null;
  retry_limit: number;
  llm_provider: "gemini" | "ollama";
  ollama_model: string;
  ollama_base_url: string;
  whisper_fallback: boolean;
  whisper_model: string;
}
