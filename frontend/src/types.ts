/** Types mirroring the FastAPI response schemas. */

export type UserRole = "hr_admin" | "recruiter" | "hiring_manager" | "viewer";

export interface User {
  id: number;
  uuid: string;
  email: string;
  full_name: string;
  role: UserRole;
  role_label: string;
  department?: string | null;
  phone?: string | null;
  avatar_url?: string | null;
  is_active: boolean;
  must_change_password: boolean;
  last_login_at?: string | null;
  created_at: string;
  permissions: string[];
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface PageMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface Page<T> {
  items: T[];
  meta: PageMeta;
}

export interface MessageResponse {
  message: string;
  detail?: string | null;
}

export type CandidateStatus =
  | "new"
  | "pending_review"
  | "reviewed"
  | "shortlisted"
  | "interviewing"
  | "offered"
  | "hired"
  | "rejected"
  | "on_hold"
  | "archived";

export interface CandidateListItem {
  id: number;
  uuid: string;
  full_name: string;
  email?: string | null;
  phone?: string | null;
  current_title?: string | null;
  current_company_name?: string | null;
  city?: string | null;
  country?: string | null;
  total_experience_years: number;
  highest_degree?: string | null;
  status: CandidateStatus;
  availability?: string | null;
  last_match_score?: number | null;
  profile_completeness?: number | null;
  top_skills: string[];
  resume_count: number;
  created_at: string;
  updated_at: string;
}

export interface SkillRead {
  id: number;
  name: string;
  canonical_name?: string | null;
  category?: string | null;
  technology_stack?: string | null;
  proficiency?: string | null;
  years_experience?: number | null;
  confidence: number;
  source: string;
  evidence?: string | null;
  in_taxonomy: boolean;
}

export interface ExperienceRead {
  id: number;
  company_name: string;
  job_title?: string | null;
  location?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  is_current: boolean;
  duration_months?: number | null;
  description?: string | null;
  technologies: string[];
}

export interface EducationRead {
  id: number;
  degree?: string | null;
  field_of_study?: string | null;
  institution?: string | null;
  start_year?: number | null;
  graduation_year?: number | null;
  grade?: string | null;
}

export interface ProjectRead {
  id: number;
  name: string;
  role?: string | null;
  description?: string | null;
  technologies: string[];
  url?: string | null;
}

export interface CertificationRead {
  id: number;
  name: string;
  issuer?: string | null;
  issue_date?: string | null;
  expiry_date?: string | null;
  credential_id?: string | null;
  url?: string | null;
}

export interface RecruiterNote {
  id: number;
  content: string;
  rating?: number | null;
  is_private: boolean;
  author_id?: number | null;
  author_name?: string | null;
  created_at: string;
}

export interface ResumeSummary {
  id: number;
  uuid: string;
  original_filename: string;
  extension: string;
  file_size: number;
  status: string;
  page_count?: number | null;
  word_count?: number | null;
  ocr_used: boolean;
  extraction_backend?: string | null;
  parse_error?: string | null;
  duplicate_of_id?: number | null;
  parse_duration_ms?: number | null;
  created_at: string;
  uploaded_by_id?: number | null;
  uploaded_by_name?: string | null;
  candidate_id?: number | null;
  download_url?: string | null;
}

export interface ResumeDetail extends ResumeSummary {
  raw_text?: string | null;
  parsed_data?: Record<string, unknown> | null;
}

export interface TimelineEntry {
  type: string;
  title: string;
  subtitle?: string | null;
  start?: string | null;
  end?: string | null;
  detail?: string | null;
}

export interface CandidateDetail extends CandidateListItem {
  address?: string | null;
  state?: string | null;
  linkedin_url?: string | null;
  github_url?: string | null;
  portfolio_url?: string | null;
  headline?: string | null;
  notice_period_days?: number | null;
  expected_ctc?: string | null;
  languages: string[];
  tags: string[];
  ai_summary?: string | null;
  ai_highlights: string[];
  graph_synced_at?: string | null;
  owner_id?: number | null;
  owner_name?: string | null;
  skills: SkillRead[];
  experiences: ExperienceRead[];
  educations: EducationRead[];
  projects: ProjectRead[];
  certifications: CertificationRead[];
  notes: RecruiterNote[];
  resumes: ResumeSummary[];
  timeline: TimelineEntry[];
}

export interface SimilarCandidate {
  candidate_id: number;
  candidate_uuid: string;
  full_name: string;
  current_title?: string | null;
  total_experience_years: number;
  shared_skills: number;
  shared_skill_names: string[];
  similarity_percent: number;
}

export interface UploadedResumeResult {
  filename: string;
  resume_id?: number | null;
  resume_uuid?: string | null;
  candidate_id?: number | null;
  status: string;
  is_duplicate: boolean;
  duplicate_of_resume_id?: number | null;
  error?: string | null;
  processing?: {
    skills_extracted: number;
    skills_normalized: number;
    experiences: number;
    educations: number;
    projects: number;
    certifications: number;
    embeddings: number;
    graph_nodes: number;
    graph_edges: number;
    duration_ms: number;
    warnings: string[];
    error?: string | null;
  } | null;
}

export interface UploadResponse {
  uploaded: number;
  duplicates: number;
  failed: number;
  queued: boolean;
  results: UploadedResumeResult[];
}

export interface MatchCriteria {
  required_skills: string[];
  mandatory_skills?: string[];
  preferred_skills?: string[];
  preferred_certifications?: string[];
  min_experience_years?: number;
  max_experience_years?: number | null;
  preferred_domain?: string | null;
  job_title?: string | null;
  job_description?: string | null;
  location?: string | null;
  education?: string | null;
  job_requirement_id?: number | null;
  top_k?: number;
  min_score?: number;
  include_explanations?: boolean;
  weights?: Record<string, number> | null;
}

export interface SkillEvidence {
  requested: string;
  matched_skill?: string | null;
  match_type: string;
  score: number;
  confidence: number;
  proficiency?: string | null;
  years_experience?: number | null;
  source?: string | null;
  evidence?: string | null;
  mandatory: boolean;
  graph_path: string[];
}

export interface ScoreComponent {
  name: string;
  score: number;
  weight: number;
  contribution: number;
  detail?: string | null;
}

export interface MatchBreakdown {
  skill_score: number;
  semantic_score: number;
  experience_score: number;
  certification_score: number;
  project_score: number;
  components: ScoreComponent[];
  weights: Record<string, number>;
}

export interface GraphContextSummary {
  connected_skills: string[];
  related_technologies: string[];
  equivalent_skills: Record<string, string>[];
  skill_hierarchy: Record<string, string>[];
  companies: string[];
  certifications: string[];
  job_roles: string[];
  similar_candidates: Record<string, unknown>[];
  retrieval_paths: string[];
}

export interface CandidateMatch {
  candidate_id: number;
  candidate_uuid: string;
  full_name: string;
  email?: string | null;
  current_title?: string | null;
  current_company?: string | null;
  location?: string | null;
  total_experience_years: number;
  highest_degree?: string | null;
  status?: string | null;
  rank: number;
  overall_score: number;
  confidence: number;
  recommendation: string;
  breakdown: MatchBreakdown;
  matched_skills: SkillEvidence[];
  related_skills: SkillEvidence[];
  missing_skills: SkillEvidence[];
  additional_skills: string[];
  explanation?: string | null;
  strengths: string[];
  gaps: string[];
  interview_questions: string[];
  learning_recommendations: string[];
  career_fit?: string | null;
  graph_context: GraphContextSummary;
}

export interface MatchResponse {
  run_id?: number | null;
  run_uuid?: string | null;
  criteria: MatchCriteria;
  total_candidates_evaluated: number;
  returned: number;
  duration_ms: number;
  generated_at: string;
  embedding_model?: string | null;
  graph_backend?: string | null;
  vector_backend?: string | null;
  llm_backend?: string | null;
  results: CandidateMatch[];
}

export interface SkillGapItem {
  skill: string;
  category?: string | null;
  candidates_with_skill: number;
  coverage_percent: number;
  demand_score: number;
  suggested_learning: string[];
}

export type SearchMode = "hybrid" | "semantic" | "keyword" | "graph" | "skill";

export interface SearchFilters {
  min_experience?: number | null;
  max_experience?: number | null;
  location?: string | null;
  current_company?: string | null;
  education?: string | null;
  certification?: string | null;
  technology?: string | null;
  availability?: string | null;
  status?: string[] | null;
  skills?: string[] | null;
}

export interface SearchRequest {
  query: string;
  mode: SearchMode;
  filters?: SearchFilters;
  sort_by?: "ai_score" | "experience" | "upload_date" | "name";
  sort_dir?: "asc" | "desc";
  page?: number;
  page_size?: number;
  include_answer?: boolean;
}

export interface SearchHit {
  candidate_id: number;
  candidate_uuid: string;
  full_name: string;
  email?: string | null;
  current_title?: string | null;
  current_company?: string | null;
  location?: string | null;
  total_experience_years: number;
  status?: string | null;
  highest_degree?: string | null;
  ai_score: number;
  keyword_score: number;
  semantic_score: number;
  graph_score: number;
  matched_skills: { skill: string; match_type: string; score: number }[];
  missing_skills: string[];
  related_skills: string[];
  snippet?: string | null;
  channels: string[];
  top_skills: string[];
}

export interface SearchResponse {
  query: string;
  mode: string;
  interpreted_skills: string[];
  interpreted_experience?: number | null;
  unknown_terms: string[];
  expanded_skills: Record<string, string>[];
  total: number;
  page: number;
  page_size: number;
  duration_ms: number;
  items: SearchHit[];
  answer?: string | null;
  answer_backend?: string | null;
  graph_paths: string[];
  generated_at: string;
}

export interface SuggestResponse {
  skills: string[];
  companies: string[];
  titles: string[];
  candidates: { id: number; full_name: string; current_title?: string | null }[];
}

export interface GraphNodeRead {
  id: string;
  label: string;
  name: string;
  properties: Record<string, unknown>;
  group?: string | null;
}

export interface GraphEdgeRead {
  source: string;
  target: string;
  relation: string;
  weight: number;
  properties: Record<string, unknown>;
}

export interface GraphView {
  nodes: GraphNodeRead[];
  edges: GraphEdgeRead[];
  focus?: string | null;
  depth: number;
  truncated: boolean;
  backend: string;
}

export interface GraphStats {
  backend: string;
  healthy: boolean;
  node_count: number;
  edge_count: number;
  node_counts: Record<string, number>;
  relationship_counts: Record<string, number>;
  last_build_at?: string | null;
  version?: number | null;
  detail?: string | null;
}

export interface SkillGraphNode {
  skill: string;
  category?: string | null;
  technology_stack?: string | null;
  parent?: string | null;
  children: string[];
  related: string[];
  job_roles: string[];
  candidate_count: number;
}

export interface SkillGraphResponse {
  total_skills: number;
  categories: Record<string, number>;
  skills: SkillGraphNode[];
  view?: GraphView | null;
}

export interface NamedValue {
  name: string;
  value: number;
  extra?: string | null;
}

export interface TrendPoint {
  period: string;
  uploads: number;
  candidates: number;
  shortlisted: number;
  rejected: number;
}

export interface ActivityItem {
  id: number;
  action: string;
  actor: string;
  description?: string | null;
  entity_type?: string | null;
  entity_id?: number | null;
  created_at: string;
  status: string;
}

export interface DashboardResponse {
  cards: {
    total_candidates: number;
    uploaded_resumes: number;
    shortlisted: number;
    rejected: number;
    pending_review: number;
    new_uploads_today: number;
    processing: number;
    failed_resumes: number;
    average_experience_years: number;
    average_match_score?: number | null;
  };
  top_skills: NamedValue[];
  technology_distribution: NamedValue[];
  experience_distribution: NamedValue[];
  candidate_status: NamedValue[];
  hiring_trends: TrendPoint[];
  top_companies: NamedValue[];
  top_certifications: NamedValue[];
  recent_activity: ActivityItem[];
  recent_uploads: Record<string, unknown>[];
  ai_recommendations: Record<string, unknown>[];
  graph: Record<string, unknown>;
  generated_at: string;
}

export interface ReportInsight {
  level: "success" | "info" | "warning" | "error" | string;
  title: string;
  detail: string;
}

export interface ReportMatchCandidate {
  candidate_id: number;
  name: string;
  score: number;
  recommendation?: string | null;
}

export interface ReportMatchRun {
  run_id: number;
  title?: string | null;
  created_at: string;
  candidates_evaluated: number;
  top_score?: number | null;
  created_by?: string | null;
  top_candidates: ReportMatchCandidate[];
}

export interface ReportResponse {
  generated_at: string;
  period_start?: string | null;
  period_end?: string | null;
  kpis: {
    total_candidates: number;
    resumes_processed: number;
    parse_success_rate: number;
    average_parse_ms: number;
    shortlist_rate: number;
    rejection_rate: number;
    hired: number;
    interviewing: number;
    pending_review: number;
    failed_resumes: number;
    average_experience_years: number;
    skills_per_candidate: number;
    taxonomy_coverage_percent: number;
    unique_skills: number;
    unique_companies: number;
    new_candidates_in_period: number;
    matches_run: number;
    average_match_score?: number | null;
  };
  insights: ReportInsight[];
  top_technologies: NamedValue[];
  top_skills: NamedValue[];
  top_categories: NamedValue[];
  hiring_trends: TrendPoint[];
  skill_gaps: SkillGapItem[];
  pipeline: { status: string; label: string; count: number; percent: number }[];
  experience_distribution: NamedValue[];
  top_companies: NamedValue[];
  top_certifications: NamedValue[];
  top_locations: NamedValue[];
  education_distribution: NamedValue[];
  recent_matches: ReportMatchRun[];
}

export interface SkillTaxonomyItem {
  id: number;
  external_id?: string | null;
  name: string;
  slug: string;
  category?: string | null;
  parent_skill?: string | null;
  technology_stack?: string | null;
  experience_level?: string | null;
  description?: string | null;
  is_technical: boolean;
  synonyms: string[];
  related_skills: string[];
  job_roles: string[];
  candidate_count: number;
}

export interface SkillCategoryItem {
  id: number;
  name: string;
  description?: string | null;
  skill_count: number;
}

export interface JobRequirement {
  id: number;
  uuid: string;
  title: string;
  department?: string | null;
  location?: string | null;
  description?: string | null;
  min_experience_years: number;
  max_experience_years?: number | null;
  required_skills: string[];
  preferred_skills: string[];
  preferred_certifications: string[];
  preferred_domain?: string | null;
  education_requirement?: string | null;
  is_active: boolean;
  created_by_id?: number | null;
  created_at: string;
  updated_at: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  environment: string;
  database: boolean;
  graph_backend: string;
  graph_healthy: boolean;
  vector_backend: string;
  embedding_model: string;
  llm_backend: string;
  skills_loaded: number;
  celery_enabled: boolean;
}

export interface AuditLogItem {
  id: number;
  action: string;
  actor: string;
  entity_type?: string | null;
  entity_id?: number | null;
  description?: string | null;
  ip_address?: string | null;
  status: string;
  created_at: string;
  meta?: Record<string, unknown> | null;
}
