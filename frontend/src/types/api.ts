export type BloomLevel =
  | "remember"
  | "understand"
  | "apply"
  | "analyze"
  | "evaluate"
  | "create";

export interface DocumentQuality {
  passed: boolean;
  page_count: number;
  text_character_count: number;
  pages_without_text: number[];
  warnings: string[];
  errors: string[];
}

export interface VisualAsset {
  asset_id: string;
  page_number: number;
  asset_type: string;
  question_eligible: boolean;
  confidence: number;
  caption?: string | null;
}

export interface DocumentManifest {
  document_id: string;
  original_filename: string;
  source_total_pages: number;
  selected_page_start: number;
  selected_page_end: number;
  pages: Array<{
    page_number: number;
    text: string;
    visual_asset_ids: string[];
  }>;
  visual_assets: VisualAsset[];
  quality: DocumentQuality;
}

export interface ContentTopic {
  topic_id: string;
  name: string;
  unit: string;
  source_pages: number[];
  supported_bloom_levels: BloomLevel[];
  evidence_chunk_ids: string[];
}

export interface ContentMap {
  subject: string;
  topics: ContentTopic[];
  course_outcomes: string[];
}

export interface BlueprintSlot {
  slot_id: string;
  question_number: string;
  section_id: string;
  marks: number;
  bloom_level: BloomLevel;
  requested_bloom_level?: BloomLevel | null;
  question_kind: string;
  topic_id: string;
  unit: string;
  evidence_chunk_ids: string[];
  requires_visual: boolean;
  visual_asset_id?: string | null;
}

export interface PaperBlueprint {
  pattern_id: string;
  subject: string;
  slots: BlueprintSlot[];
  warnings: string[];
}

export interface PreparationResponse {
  manifest: DocumentManifest;
  content_map: ContentMap;
  blueprint: PaperBlueprint;
}

export interface FullWorkflowResponse extends PreparationResponse {
  pdf_download_url: string;
  paper: {
    title: string;
    subject_family: string;
    total_marks: number;
    requires_human_approval: boolean;
    publication_ready: boolean;
    questions: Array<{
      question_id: string;
      slot_id: string;
      question_number: string;
      section_id: string;
      question_kind: string;
      question_text: string;
      marks: number;
      bloom_level: BloomLevel;
      visual_asset_id?: string | null;
      accepted: boolean;
      quality_score?: number | null;
      findings: Array<{
        code: string;
        severity: "error" | "warning" | "info";
        message: string;
      }>;
    }>;
  };
}
