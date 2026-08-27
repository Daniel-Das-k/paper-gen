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
  facet?: string | null;
  source_pages: number[];
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

export interface MarkingCriterion {
  criterion: string;
  marks: number;
}

export interface AnswerKeyEntry {
  question_id: string;
  question_number: string;
  section_id: string;
  marks: number;
  criteria: MarkingCriterion[];
  answer: string;
}

export interface GeneratedSet {
  set_label?: string | null;
  answer_key?: AnswerKeyEntry[];
  pdf_download_url: string;
  scheme_download_url: string;
  docx_download_url?: string | null;
}

export interface FullWorkflowResponse extends PreparationResponse {
  pdf_download_url: string;
  scheme_download_url: string;
  docx_download_url?: string | null;
  answer_key?: AnswerKeyEntry[];
  sets?: GeneratedSet[];
  cross_set_warnings?: string[];
  selected_set_label?: string | null;
  paper: {
    title: string;
    set_label?: string | null;
    subject: string;
    subject_family: string;
    duration_minutes: number;
    total_marks: number;
    exam_header: ExamHeader;
    requires_human_approval: boolean;
    publication_ready: boolean;
    course_outcome_coverage?: {
      marks_by_outcome: Record<string, number>;
      unmapped_marks: number;
      total_marks: number;
    };
    bloom_summary?: {
      requested: Record<string, number>;
      observed: Record<string, number>;
      deviations: number;
      total: number;
      unverified: number;
    };
    questions: Array<{
      question_id: string;
      slot_id: string;
      question_number: string;
      section_id: string;
      question_kind: string;
      question_text: string;
      marks: number;
      bloom_level: BloomLevel;
      observed_bloom_level?: BloomLevel | null;
      bloom_matches_blueprint?: boolean;
      course_outcome?: string | null;
      course_outcome_code?: string | null;
      visual_asset_id?: string | null;
      accepted: boolean;
      faculty_modified?: boolean;
      quality_score?: number | null;
      quality_dimensions?: {
        grounding: number;
        correctness: number;
        clarity: number;
        marks_fit: number;
        bloom_alignment: number;
        originality: number;
        answer_scheme: number;
        visual_relevance?: number | null;
      } | null;
      findings: Array<{
        code: string;
        severity: "error" | "warning" | "info";
        message: string;
      }>;
    }>;
  };
}

export interface ExamHeader {
  college: string;
  institution_line: string;
  affiliation: string;
  exam_title: string;
  year: string;
  semester: string;
  branch: string;
  subject_code: string;
  subject_name: string;
  qp_code: string;
  regulation: string;
  common_to: string;
  date: string;
  register_number_boxes: number;
}

export type DemoRole = "faculty" | "hod" | "coe";
export interface DemoUser {
  username: string;
  displayName: string;
  role: DemoRole;
}
export type DemoPaperStatus =
  | "draft"
  | "faculty_finalized"
  | "submitted_to_hod"
  | "submitted_to_coe"
  | "approved";

export interface DemoJob {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  stage: string;
  progress: number;
  error?: string | null;
  paper_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface DemoPaperSummary {
  id: string;
  pattern_id: string;
  subject: string;
  course_code: string;
  course_name: string;
  exam_label: string;
  year: string;
  semester: string;
  department: string;
  generated_by: string;
  last_action: string;
  hod_approved: boolean;
  last_coe_action: string;
  status: DemoPaperStatus;
  created_at: string;
  updated_at: string;
}

export interface DemoActivity {
  actor_role: DemoRole;
  action: string;
  comment: string;
  created_at: string;
}

export interface DemoPaperRecord extends DemoPaperSummary {
  result: FullWorkflowResponse;
  activities: DemoActivity[];
}

export interface PaperPatternSection {
  section_id: string;
  title: string;
  unit_number?: string | null;
  question_kind: string;
  question_count: number;
  marks_each: number;
  answers_required: number;
  choices_per_question: number;
}

export interface PaperPattern {
  pattern_id: string;
  name: string;
  duration_minutes: number;
  total_marks: number;
  sections: PaperPatternSection[];
}

export interface SyllabusUnit {
  number: string;
  title: string;
  topics: string;
}

export interface SyllabusExtraction {
  subject_code?: string | null;
  subject_name?: string | null;
  regulation?: string | null;
  units: SyllabusUnit[];
  course_outcomes: string[];
  extraction_confident: boolean;
  problem?: string | null;
}

export interface UnitUpload {
  unit: string;
  file: File | null;
  startPage: string;
  endPage: string;
}
