import { api, downloadBlob } from "./client";
import type {
  AuditLogItem,
  CandidateDetail,
  CandidateListItem,
  CandidateMatch,
  DashboardResponse,
  GraphStats,
  GraphView,
  HealthResponse,
  JobRequirement,
  MatchCriteria,
  MatchResponse,
  MessageResponse,
  Page,
  ReportResponse,
  ResumeDetail,
  ResumeSummary,
  SearchRequest,
  SearchResponse,
  SimilarCandidate,
  SkillCategoryItem,
  SkillGapItem,
  SkillGraphResponse,
  SkillTaxonomyItem,
  SuggestResponse,
  TokenResponse,
  UploadResponse,
  User,
} from "@/types";

// ------------------------------------------------------------------ auth
export const authApi = {
  login: (email: string, password: string, remember_me = false) =>
    api.post<TokenResponse>("/login", { email, password, remember_me }).then((r) => r.data),
  me: () => api.get<User>("/me").then((r) => r.data),
  logout: (all_sessions = false) =>
    api.post<MessageResponse>("/logout", { all_sessions }).then((r) => r.data),
  sessions: () => api.get<Record<string, unknown>[]>("/me/sessions").then((r) => r.data),
  forgotPassword: (email: string) =>
    api
      .post<{ message: string; reset_token?: string | null }>("/forgot-password", { email })
      .then((r) => r.data),
  resetPassword: (token: string, new_password: string) =>
    api.post<MessageResponse>("/reset-password", { token, new_password }).then((r) => r.data),
  changePassword: (current_password: string, new_password: string) =>
    api
      .post<MessageResponse>("/change-password", { current_password, new_password })
      .then((r) => r.data),
};

// ------------------------------------------------------------------ users
export interface UserCreatePayload {
  email: string;
  full_name: string;
  password: string;
  role: string;
  department?: string;
  phone?: string;
  is_active?: boolean;
  must_change_password?: boolean;
}

export const usersApi = {
  list: () => api.get<User[]>("/users").then((r) => r.data),
  create: (payload: UserCreatePayload) => api.post<User>("/users", payload).then((r) => r.data),
  update: (id: number, payload: Partial<UserCreatePayload>) =>
    api.put<User>(`/users/${id}`, payload).then((r) => r.data),
  deactivate: (id: number) => api.delete<MessageResponse>(`/users/${id}`).then((r) => r.data),
  auditLogs: (params: { page?: number; page_size?: number; action?: string } = {}) =>
    api
      .get<{ items: AuditLogItem[]; meta: { page: number; page_size: number; total: number } }>(
        "/users/audit/logs",
        { params },
      )
      .then((r) => r.data),
};

// --------------------------------------------------------------- resumes
export const resumesApi = {
  upload: (files: File[], options: { wait?: boolean; allowDuplicates?: boolean } = {}) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    return api
      .post<UploadResponse>("/upload", form, {
        params: { wait: options.wait ?? false, allow_duplicates: options.allowDuplicates ?? false },
        timeout: 600_000,
      })
      .then((r) => r.data);
  },
  list: (params: { page?: number; page_size?: number; status?: string } = {}) =>
    api.get<Page<ResumeSummary>>("/resumes", { params }).then((r) => r.data),
  get: (id: number) => api.get<ResumeDetail>(`/resume/${id}`).then((r) => r.data),
  status: (id: number) =>
    api.get<{ status: string; progress: number; error?: string | null }>(`/resume/${id}/status`).then((r) => r.data),
  reprocess: (id: number) => api.post<Record<string, unknown>>(`/resume/${id}/reprocess`).then((r) => r.data),
  remove: (id: number) => api.delete<MessageResponse>(`/resume/${id}`).then((r) => r.data),
  download: async (id: number, filename: string) => {
    const response = await api.get(`/resume/${id}/download`, { responseType: "blob" });
    downloadBlob(response.data as Blob, filename);
  },
};

// ------------------------------------------------------------ candidates
export interface CandidateQuery {
  search?: string;
  status?: string[];
  skills?: string[];
  min_experience?: number;
  max_experience?: number;
  location?: string;
  company?: string;
  education?: string;
  certification?: string;
  technology?: string;
  availability?: string;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  page?: number;
  page_size?: number;
}

export const candidatesApi = {
  list: (params: CandidateQuery) =>
    api
      .get<Page<CandidateListItem>>("/candidates", {
        params,
        paramsSerializer: { indexes: null },
      })
      .then((r) => r.data),
  get: (id: number) => api.get<CandidateDetail>(`/candidate/${id}`).then((r) => r.data),
  update: (id: number, payload: Record<string, unknown>) =>
    api.put<CandidateDetail>(`/candidate/${id}`, payload).then((r) => r.data),
  changeStatus: (id: number, status: string, reason?: string) =>
    api.patch<CandidateDetail>(`/candidate/${id}/status`, { status, reason }).then((r) => r.data),
  remove: (id: number, hard = false) =>
    api.delete<MessageResponse>(`/candidate/${id}`, { params: { hard } }).then((r) => r.data),
  addNote: (id: number, content: string, rating?: number, is_private = false) =>
    api.post(`/candidate/${id}/notes`, { content, rating, is_private }).then((r) => r.data),
  score: (id: number, criteria: MatchCriteria) =>
    api.post<CandidateMatch>(`/candidate/${id}/score`, criteria).then((r) => r.data),
  similar: (id: number, limit = 5) =>
    api
      .get<SimilarCandidate[]>(`/candidate/${id}/similar`, { params: { limit } })
      .then((r) => r.data),
};

// -------------------------------------------------------------- matching
export const matchingApi = {
  run: (criteria: MatchCriteria) => api.post<MatchResponse>("/skill-match", criteria).then((r) => r.data),
  runs: (limit = 20) =>
    api.get<Record<string, unknown>[]>("/skill-match/runs", { params: { limit } }).then((r) => r.data),
  run_detail: (id: number) => api.get<Record<string, unknown>>(`/skill-match/runs/${id}`).then((r) => r.data),
  gapAnalysis: (skills: string[]) =>
    api.post<SkillGapItem[]>("/skill-match/gap-analysis", skills).then((r) => r.data),
};

// ---------------------------------------------------------------- search
export const searchApi = {
  search: (request: SearchRequest) => api.post<SearchResponse>("/search", request).then((r) => r.data),
  suggest: (q: string, limit = 8) =>
    api.get<SuggestResponse>("/search/suggest", { params: { q, limit } }).then((r) => r.data),
};

// ----------------------------------------------------------------- graph
export const graphApi = {
  stats: () => api.get<GraphStats>("/graph/stats").then((r) => r.data),
  build: (clear = true) =>
    api.post<Record<string, unknown>>("/graph/build", { clear }).then((r) => r.data),
  overview: (limit = 220, candidates = 25) =>
    api.get<GraphView>("/graph/overview", { params: { limit, candidates } }).then((r) => r.data),
  candidate: (id: number, depth = 2) =>
    api.get<GraphView>(`/graph/candidate/${id}`, { params: { depth } }).then((r) => r.data),
  skill: (name: string, depth = 2) =>
    api.get<GraphView>(`/graph/skill/${encodeURIComponent(name)}`, { params: { depth } }).then((r) => r.data),
  skills: (limit = 200) =>
    api.get<SkillGraphResponse>("/graph/skills", { params: { limit } }).then((r) => r.data),
};

// ------------------------------------------------------ dashboard/reports
export const dashboardApi = {
  get: () => api.get<DashboardResponse>("/dashboard").then((r) => r.data),
};

export const reportsApi = {
  get: (params: { months?: number; gap_skills?: string[] } = {}) =>
    api.get<ReportResponse>("/reports", { params }).then((r) => r.data),
  export: async (format: "pdf" | "csv" | "excel", months = 6) => {
    const response = await api.get("/reports/export", {
      params: { format, months },
      responseType: "blob",
    });
    const extension = format === "excel" ? "xlsx" : format;
    downloadBlob(response.data as Blob, `recruitment-report.${extension}`);
  },
  exportCandidates: async (candidateIds?: number[]) => {
    const response = await api.get("/reports/candidates/export", {
      params: { candidate_ids: candidateIds },
      responseType: "blob",
    });
    downloadBlob(response.data as Blob, "candidates.csv");
  },
};

// ---------------------------------------------------------------- skills
export const skillsApi = {
  list: (params: { search?: string; category?: string; limit?: number } = {}) =>
    api.get<SkillTaxonomyItem[]>("/skills", { params }).then((r) => r.data),
  categories: () => api.get<SkillCategoryItem[]>("/skills/categories").then((r) => r.data),
  stats: () => api.get<Record<string, unknown>>("/skills/stats").then((r) => r.data),
  reimport: (generate_embeddings = true) =>
    api
      .post<Record<string, unknown>>("/skills/import", null, { params: { generate_embeddings } })
      .then((r) => r.data),
  uploadCsv: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api
      .post<Record<string, unknown>>("/skills/import/upload", form)
      .then((r) => r.data);
  },
};

// ------------------------------------------------------ job requirements
export const jobsApi = {
  list: (activeOnly = true) =>
    api.get<JobRequirement[]>("/job-requirements", { params: { active_only: activeOnly } }).then((r) => r.data),
  create: (payload: Partial<JobRequirement>) =>
    api.post<JobRequirement>("/job-requirements", payload).then((r) => r.data),
  update: (id: number, payload: Partial<JobRequirement>) =>
    api.put<JobRequirement>(`/job-requirements/${id}`, payload).then((r) => r.data),
  remove: (id: number) => api.delete<MessageResponse>(`/job-requirements/${id}`).then((r) => r.data),
};

// ---------------------------------------------------------------- system
export const systemApi = {
  health: () => api.get<HealthResponse>("/health").then((r) => r.data),
  info: () => api.get<Record<string, any>>("/system/info").then((r) => r.data),
};
