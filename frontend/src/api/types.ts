export type ConfidenceLevel = 'high' | 'medium' | 'low' | 'uncertain';
export type ReviewStatus = 'pending' | 'needs_review' | 'approved' | 'rejected';
export type ContentType = 'reading_material' | 'coding_question' | 'project' | 'other';
export type TagRole =
  | 'explain'
  | 'practice'
  | 'example'
  | 'assessment'
  | 'project'
  | 'syntax'
  | 'prerequisite';

export interface KnowledgePoint {
  source_kp_id: string;
  knowledge_node_id?: string;
  label: string;
  label_enum?: string;
  description?: string;
}

export interface KnowledgePointWithCounts extends KnowledgePoint {
  mapped_content_count: number;
  tag_role_breakdown: Partial<Record<TagRole, number>>;
}

export interface ProposedTag {
  source_kp_id: string;
  label?: string;
  tag_role: TagRole;
  confidence: ConfidenceLevel;
  rationale?: string;
}

export interface AiResult {
  content_id: string;
  proposed_tags: ProposedTag[];
  overall_confidence: ConfidenceLevel;
  needs_human_review: boolean;
  review_reasons?: string[];
  provider?: string;
  model?: string;
}

export interface Mapping {
  id?: number;
  content_id: string;
  file_path: string;
  content_type: ContentType;
  title: string;
  topic_name?: string;
  course_title?: string;
  ai_result?: AiResult;
  human_tags: ProposedTag[];
  review_status: ReviewStatus;
  reviewer_notes?: string;
  updated_at?: string;
}

export interface MappingsResponse {
  stats: {
    total: number;
    pending_review: number;
    flagged_for_human: number;
    approved: number;
  };
  total: number;
  items: Mapping[];
}

export interface Course {
  course_id: string;
  course_title: string;
  kp_count: number;
  content_count: number;
  mapped_count: number;
}

export interface CoursesResponse {
  courses: Course[];
}

export interface KpsWithCountsResponse {
  count: number;
  knowledge_points: KnowledgePointWithCounts[];
}

export interface InterviewQuestion {
  id: number;
  row_key: string;
  question_uuid?: string | null;
  question: string;
  question_type?: string | null;
  skills_assessed_remarks?: string | null;
  remarks?: string | null;
  company_name?: string | null;
  role?: string | null;
  tech_stack?: string | null;
  optional_skills?: string | null;
  interview_date?: string | null;
  product?: string | null;
  job_type?: string | null;
  job_id?: string | null;
  minimum_ctc_lpa?: string | null;
  maximum_ctc_lpa?: string | null;
  round_category?: string | null;
  interview_process?: string | null;
  group_key?: string | null;
  group_representative_row_key?: string | null;
  member_count?: number | null;
  canonical_question?: string | null;
  canonical_slug?: string | null;
  group_normalized?: number | null;
  theory?: {
    row_key?: string | null;
    verdict?: TheoryVerdict | string | null;
    overall_confidence?: number | null;
    review_status?: ReviewStatus | string | null;
    updated_at?: string | null;
    question_type?: 'THEORY' | 'CODING' | string | null;
    synthesis_quality?:
      | 'complete'
      | 'partial'
      | 'insufficient'
      | 'skipped'
      | string
      | null;
    match_strategy?: string | null;
  } | null;
  first_seen_at?: string;
  last_seen_at?: string;
  updated_at?: string;
}

export interface QuestionGroup {
  group_key: string;
  exact_question: string;
  company_name?: string | null;
  canonical_question?: string | null;
  canonical_slug?: string | null;
  normalized: number;
  normalizer_version?: string | null;
  merged_into?: string | null;
  member_count: number;
  representative_row_key: string;
  first_seen_at: string;
  last_seen_at: string;
  created_at: string;
  updated_at: string;
}

export interface QuestionGroupMember {
  row_key: string;
  question_uuid?: string | null;
  question: string;
  company_name?: string | null;
  role?: string | null;
  interview_date?: string | null;
  first_seen_at?: string;
}

export interface NormalizeStatus {
  pending: number;
  normalized: number;
  merged: number;
  total: number;
}

export interface InterviewQuestionsResponse {
  total: number;
  filtered_total: number;
  returned: number;
  items: InterviewQuestion[];
  group_by?: boolean;
  applied_date_range: {
    duration: string | null;
    date_from: string | null;
    date_to: string | null;
  };
}

export interface InterviewFacets {
  companies: string[];
  roles: string[];
  question_types: string[];
  tech_stacks: string[];
  products: string[];
}

export interface InterviewSyncLog {
  id: number;
  started_at: string;
  finished_at?: string | null;
  status: 'running' | 'success' | 'error';
  trigger: 'manual' | 'scheduled';
  fetched_rows: number;
  inserted: number;
  updated: number;
  unchanged: number;
  error?: string | null;
  duration_ms?: number;
}

export interface InterviewSyncStatus {
  last: InterviewSyncLog | null;
  recent: InterviewSyncLog[];
  schedule: { hour_utc: number; minute_utc: number; trigger: string };
}

export type TheoryVerdict = 'covered' | 'not_covered';

export interface TheoryRequiredKp {
  source_kp_id: string;
  confidence?: ConfidenceLevel | string;
  rationale?: string;
  label?: string;
}

export interface TheoryCitation {
  content_id: string;
  title?: string;
  topic_name?: string | null;
  kp_id?: string;
  tag_role?: string;
  snippet?: string;
  content_type?: string;
}

export interface TheoryTag {
  id?: number;
  row_key: string;
  question_text: string;
  verdict: TheoryVerdict;
  can_student_answer: boolean;
  rationale: string;
  overall_confidence: number;
  ai_model?: string;
  prompt_version?: string;
  review_status: ReviewStatus;
  review_reasons: string[];
  required_kps: TheoryRequiredKp[];
  citations: TheoryCitation[];
  candidate_citations: TheoryCitation[];
  rejected_candidates?: TheoryCitation[];
  kp_identifier_reasoning?: string | null;
  judge_reasoning?: string | null;
  // Stage 3 — AnswerSynthesizer
  question_type?: 'THEORY' | 'CODING' | string;
  synthesized_answer?: string | null;
  answer_grounding?: { claim: string; content_ids: string[] }[];
  synthesis_quality?: 'complete' | 'partial' | 'insufficient' | 'skipped' | string;
  synthesis_confidence?: number;
  synthesis_reasoning?: string | null;
  match_strategy?: 'exact_match' | 'partial_match' | 'combined' | 'none' | '' | string;
  human_required_kps: TheoryRequiredKp[];
  human_citations: TheoryCitation[];
  human_verdict?: TheoryVerdict | null;
  reviewer_notes?: string | null;
  created_at?: string;
  updated_at?: string;
  group_key?: string | null;
  group_member_count?: number | null;
  group_canonical_question?: string | null;
  group_canonical_slug?: string | null;
  interview?: {
    company_name?: string | null;
    role?: string | null;
    question_type?: string | null;
    interview_date?: string | null;
    tech_stack?: string | null;
  };
}

export type FeedbackType =
  | 'wrong_verdict'
  | 'missing_kp'
  | 'wrong_kp'
  | 'missing_citation'
  | 'wrong_citation'
  | 'general';

export type FeedbackSeverity = 'low' | 'medium' | 'high';

export interface FeedbackEntry {
  id: number;
  row_key: string;
  prompt_version: string;
  feedback_type: FeedbackType | string;
  feedback_text: string;
  severity: FeedbackSeverity | string;
  ai_verdict_at_time?: string | null;
  human_verdict?: string | null;
  added_by?: string;
  created_at: string;
}

export interface TagHistoryEntry {
  id: number;
  row_key: string;
  prompt_version: string;
  ai_model?: string | null;
  verdict: TheoryVerdict | string;
  overall_confidence: number;
  required_kps: TheoryRequiredKp[];
  citations: TheoryCitation[];
  candidate_citations: TheoryCitation[];
  rejected_candidates: TheoryCitation[];
  rationale?: string | null;
  judge_reasoning?: string | null;
  kp_identifier_reasoning?: string | null;
  review_reasons: string[];
  question_type?: 'THEORY' | 'CODING' | string;
  synthesized_answer?: string | null;
  answer_grounding?: { claim: string; content_ids: string[] }[];
  synthesis_quality?: 'complete' | 'partial' | 'insufficient' | 'skipped' | string;
  synthesis_confidence?: number;
  synthesis_reasoning?: string | null;
  match_strategy?: string | null;
  created_at: string;
}

export interface ImprovementTrendPoint {
  prompt_version: string;
  agreement_rate: number;
  total: number;
  trigger: string;
  created_at: string;
}

export interface ImprovementSummary {
  fixed: number;
  regressed: number;
  rows_with_history: number;
  total_golds: number;
  trend: ImprovementTrendPoint[];
}

export interface TheoryListResponse {
  total: number;
  returned: number;
  items: TheoryTag[];
  stats: {
    by_status: Record<string, number>;
    by_verdict: Record<string, number>;
  };
  applied_date_range: {
    duration: string | null;
    date_from: string | null;
    date_to: string | null;
  };
}

export interface TheoryPromptVersion {
  id: number;
  version: string;
  fewshot_count: number;
  gold_count_at_compile: number;
  devset_agreement: number | null;
  notes: string;
  is_active: number;
  created_at: string;
}

export interface TheoryEvalRun {
  id: number;
  prompt_version: string;
  model: string;
  trigger: string;
  total: number;
  verdict_agree: number;
  false_covered: number;
  false_not_covered: number;
  kp_jaccard_avg: number;
  avg_confidence: number;
  agreement_rate: number;
  created_at: string;
}
