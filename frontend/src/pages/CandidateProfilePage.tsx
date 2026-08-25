import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Grid,
  IconButton,
  Link,
  MenuItem,
  Rating,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableRow,
  Tabs,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import DownloadIcon from "@mui/icons-material/Download";
import GitHubIcon from "@mui/icons-material/GitHub";
import LanguageIcon from "@mui/icons-material/Language";
import LinkedInIcon from "@mui/icons-material/LinkedIn";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import PhoneIphoneIcon from "@mui/icons-material/PhoneIphone";
import PlaceIcon from "@mui/icons-material/Place";
import { useSnackbar } from "notistack";
import dayjs from "dayjs";

import { candidatesApi, graphApi, resumesApi } from "@/api/endpoints";
import GraphCanvas from "@/components/GraphCanvas";
import { EmptyState, ErrorState, Loading, ScoreBadge, SectionCard, StatusChip } from "@/components/common";
import { useAuth } from "@/auth/AuthContext";
import type { SkillRead } from "@/types";

const STATUS_OPTIONS = [
  "new",
  "pending_review",
  "reviewed",
  "shortlisted",
  "interviewing",
  "offered",
  "hired",
  "rejected",
  "on_hold",
];

function groupSkills(skills: SkillRead[]): [string, SkillRead[]][] {
  const groups = new Map<string, SkillRead[]>();
  skills.forEach((skill) => {
    const key = skill.category ?? "Other";
    groups.set(key, [...(groups.get(key) ?? []), skill]);
  });
  return [...groups.entries()].sort((a, b) => b[1].length - a[1].length);
}

function formatRange(start?: string | null, end?: string | null, current?: boolean): string {
  const from = start ? dayjs(start).format("MMM YYYY") : "—";
  const to = current ? "Present" : end ? dayjs(end).format("MMM YYYY") : "—";
  return `${from} – ${to}`;
}

export default function CandidateProfilePage() {
  const { candidateId } = useParams();
  const id = Number(candidateId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { enqueueSnackbar } = useSnackbar();
  const { can } = useAuth();

  const [tab, setTab] = useState(0);
  const [note, setNote] = useState("");
  const [rating, setRating] = useState<number | null>(null);
  const [resumeToDelete, setResumeToDelete] = useState<{ id: number; filename: string } | null>(null);
  const canDeleteResume = can("resume:upload");

  const candidate = useQuery({
    queryKey: ["candidate", id],
    queryFn: () => candidatesApi.get(id),
    enabled: Number.isFinite(id),
  });

  const similar = useQuery({
    queryKey: ["candidate", id, "similar"],
    queryFn: () => candidatesApi.similar(id, 5),
    enabled: Number.isFinite(id) && tab === 4,
  });

  const graph = useQuery({
    queryKey: ["candidate", id, "graph"],
    queryFn: () => graphApi.candidate(id, 2),
    enabled: Number.isFinite(id) && tab === 5,
  });

  const changeStatus = useMutation({
    mutationFn: (status: string) => candidatesApi.changeStatus(id, status),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["candidate", id] });
      void queryClient.invalidateQueries({ queryKey: ["candidates"] });
      enqueueSnackbar("Status updated", { variant: "success" });
    },
    onError: (error: Error) => enqueueSnackbar(error.message, { variant: "error" }),
  });

  const addNote = useMutation({
    mutationFn: () => candidatesApi.addNote(id, note, rating ?? undefined),
    onSuccess: () => {
      setNote("");
      setRating(null);
      void queryClient.invalidateQueries({ queryKey: ["candidate", id] });
      enqueueSnackbar("Note added", { variant: "success" });
    },
    onError: (error: Error) => enqueueSnackbar(error.message, { variant: "error" }),
  });

  const deleteResume = useMutation({
    mutationFn: (resumeId: number) => resumesApi.remove(resumeId),
    onSuccess: () => {
      setResumeToDelete(null);
      void queryClient.invalidateQueries({ queryKey: ["candidate", id] });
      void queryClient.invalidateQueries({ queryKey: ["candidates"] });
      enqueueSnackbar("Resume deleted", { variant: "success" });
    },
    onError: (error: Error) => enqueueSnackbar(error.message, { variant: "error" }),
  });

  if (candidate.isLoading) return <Loading label="Loading candidate profile…" height={400} />;
  if (candidate.error || !candidate.data) return <ErrorState error={candidate.error} onRetry={candidate.refetch} />;

  const data = candidate.data;
  const location = [data.city, data.state, data.country].filter(Boolean).join(", ");

  return (
    <>
      <Stack direction="row" alignItems="center" gap={1}>
        <IconButton onClick={() => navigate("/candidates")} aria-label="Back to candidates">
          <ArrowBackIcon />
        </IconButton>
        <Typography variant="body2" color="text.secondary">
          Back to candidates
        </Typography>
      </Stack>

      <Card>
        <CardContent>
          <Grid container spacing={3} alignItems="flex-start">
            <Grid item>
              <Avatar sx={{ width: 78, height: 78, fontSize: 30, bgcolor: "primary.main" }}>
                {data.full_name.charAt(0)}
              </Avatar>
            </Grid>
            <Grid item xs>
              <Stack direction="row" gap={1.5} alignItems="center" flexWrap="wrap">
                <Typography variant="h1">{data.full_name}</Typography>
                <StatusChip status={data.status} />
                {data.last_match_score != null ? <ScoreBadge score={data.last_match_score} /> : null}
              </Stack>
              <Typography variant="h4" color="text.secondary" sx={{ mt: 0.5, fontWeight: 500 }}>
                {data.current_title ?? "Role not detected"}
                {data.current_company_name ? ` · ${data.current_company_name}` : ""}
              </Typography>

              <Stack direction="row" gap={2.5} flexWrap="wrap" sx={{ mt: 1.5 }}>
                {data.email ? (
                  <Stack direction="row" gap={0.75} alignItems="center">
                    <MailOutlineIcon fontSize="small" color="action" />
                    <Link href={`mailto:${data.email}`} variant="body2" underline="hover">
                      {data.email}
                    </Link>
                  </Stack>
                ) : null}
                {data.phone ? (
                  <Stack direction="row" gap={0.75} alignItems="center">
                    <PhoneIphoneIcon fontSize="small" color="action" />
                    <Typography variant="body2">{data.phone}</Typography>
                  </Stack>
                ) : null}
                {location ? (
                  <Stack direction="row" gap={0.75} alignItems="center">
                    <PlaceIcon fontSize="small" color="action" />
                    <Typography variant="body2">{location}</Typography>
                  </Stack>
                ) : null}
                {data.linkedin_url ? (
                  <Tooltip title="LinkedIn">
                    <IconButton size="small" href={data.linkedin_url} target="_blank" rel="noreferrer">
                      <LinkedInIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                ) : null}
                {data.github_url ? (
                  <Tooltip title="GitHub">
                    <IconButton size="small" href={data.github_url} target="_blank" rel="noreferrer">
                      <GitHubIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                ) : null}
                {data.portfolio_url ? (
                  <Tooltip title="Portfolio">
                    <IconButton size="small" href={data.portfolio_url} target="_blank" rel="noreferrer">
                      <LanguageIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                ) : null}
              </Stack>
            </Grid>
            <Grid item xs={12} md="auto">
              <Stack gap={1.5} direction={{ xs: "row", md: "column" }} flexWrap="wrap">
                <TextField
                  select
                  label="Status"
                  size="small"
                  value={data.status}
                  disabled={!can("candidate:write") || changeStatus.isPending}
                  onChange={(event) => changeStatus.mutate(event.target.value)}
                  sx={{ minWidth: 190 }}
                >
                  {STATUS_OPTIONS.map((status) => (
                    <MenuItem key={status} value={status}>
                      {status.replace(/_/g, " ")}
                    </MenuItem>
                  ))}
                </TextField>
                {data.resumes[0] ? (
                  <>
                    <Button
                      variant="outlined"
                      startIcon={<DownloadIcon />}
                      onClick={() =>
                        resumesApi.download(data.resumes[0].id, data.resumes[0].original_filename)
                      }
                    >
                      Download resume
                    </Button>
                    {canDeleteResume ? (
                      <Button
                        variant="outlined"
                        color="error"
                        startIcon={<DeleteOutlineIcon />}
                        disabled={deleteResume.isPending}
                        onClick={() =>
                          setResumeToDelete({
                            id: data.resumes[0].id,
                            filename: data.resumes[0].original_filename,
                          })
                        }
                      >
                        Delete resume
                      </Button>
                    ) : null}
                  </>
                ) : null}
              </Stack>
            </Grid>
          </Grid>

          <Grid container spacing={2} sx={{ mt: 1 }}>
            {[
              { label: "Experience", value: `${data.total_experience_years.toFixed(1)} yrs` },
              { label: "Skills", value: data.skills.length },
              { label: "Education", value: data.highest_degree ?? "—" },
              { label: "Certifications", value: data.certifications.length },
              { label: "Profile completeness", value: `${Math.round(data.profile_completeness ?? 0)}%` },
            ].map((item) => (
              <Grid item xs={6} md={2.4} key={item.label}>
                <Typography variant="caption" color="text.secondary">
                  {item.label}
                </Typography>
                <Typography variant="h4">{item.value}</Typography>
              </Grid>
            ))}
          </Grid>
        </CardContent>
      </Card>

      {data.ai_summary ? (
        <Card sx={{ borderLeft: "4px solid", borderLeftColor: "secondary.main" }}>
          <CardContent>
            <Typography variant="h4">AI summary</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {data.ai_summary}
            </Typography>
            {data.ai_highlights.length ? (
              <Stack direction="row" gap={1} flexWrap="wrap" sx={{ mt: 1.5 }}>
                {data.ai_highlights.map((highlight) => (
                  <Chip key={highlight} size="small" color="secondary" variant="outlined" label={highlight} />
                ))}
              </Stack>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <Tabs
          value={tab}
          onChange={(_event, value) => setTab(value)}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ px: 2, borderBottom: "1px solid", borderColor: "divider" }}
        >
          <Tab label="Skills" />
          <Tab label="Experience" />
          <Tab label="Education & Projects" />
          <Tab label="Notes" />
          <Tab label="Similar candidates" />
          <Tab label="Knowledge graph" />
          <Tab label="Resume" />
        </Tabs>

        <CardContent>
          {tab === 0 ? (
            <Stack gap={3}>
              {groupSkills(data.skills).map(([category, skills]) => (
                <Box key={category}>
                  <Typography variant="h5" sx={{ mb: 1 }}>
                    {category}
                    <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                      {skills.length}
                    </Typography>
                  </Typography>
                  <Stack direction="row" gap={1} flexWrap="wrap">
                    {skills.map((skill) => (
                      <Tooltip
                        key={skill.id}
                        title={
                          skill.evidence
                            ? `${skill.evidence} · confidence ${Math.round(skill.confidence * 100)}%`
                            : `Confidence ${Math.round(skill.confidence * 100)}%`
                        }
                      >
                        <Chip
                          label={
                            skill.years_experience
                              ? `${skill.name} · ${skill.years_experience}y`
                              : skill.name
                          }
                          color={skill.in_taxonomy ? "primary" : "default"}
                          variant={skill.confidence >= 0.9 ? "filled" : "outlined"}
                          size="small"
                        />
                      </Tooltip>
                    ))}
                  </Stack>
                </Box>
              ))}
            </Stack>
          ) : null}

          {tab === 1 ? (
            <Stack gap={2.5}>
              {data.experiences.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  No work history was detected in the resume.
                </Typography>
              ) : (
                data.experiences.map((experience) => (
                  <Box
                    key={experience.id}
                    sx={{ pl: 2, borderLeft: "2px solid", borderColor: "divider", position: "relative" }}
                  >
                    <Box
                      sx={{
                        position: "absolute",
                        left: -6,
                        top: 6,
                        width: 10,
                        height: 10,
                        borderRadius: "50%",
                        bgcolor: experience.is_current ? "success.main" : "primary.main",
                      }}
                    />
                    <Typography variant="h5">{experience.job_title ?? "Role"}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {experience.company_name}
                      {experience.location ? ` · ${experience.location}` : ""} ·{" "}
                      {formatRange(experience.start_date, experience.end_date, experience.is_current)}
                      {experience.duration_months
                        ? ` · ${(experience.duration_months / 12).toFixed(1)} yrs`
                        : ""}
                    </Typography>
                    {experience.description ? (
                      <Typography variant="body2" sx={{ mt: 1, whiteSpace: "pre-line" }}>
                        {experience.description}
                      </Typography>
                    ) : null}
                    {experience.technologies.length ? (
                      <Stack direction="row" gap={0.5} flexWrap="wrap" sx={{ mt: 1 }}>
                        {experience.technologies.map((tech) => (
                          <Chip key={tech} size="small" variant="outlined" label={tech} />
                        ))}
                      </Stack>
                    ) : null}
                  </Box>
                ))
              )}
            </Stack>
          ) : null}

          {tab === 2 ? (
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Typography variant="h5" sx={{ mb: 1.5 }}>
                  Education
                </Typography>
                <Table size="small">
                  <TableBody>
                    {data.educations.map((education) => (
                      <TableRow key={education.id}>
                        <TableCell>
                          <Typography variant="body2" fontWeight={600}>
                            {education.degree ?? "Degree"}
                            {education.field_of_study ? ` · ${education.field_of_study}` : ""}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {education.institution ?? "—"}
                            {education.graduation_year ? ` · ${education.graduation_year}` : ""}
                            {education.grade ? ` · ${education.grade}` : ""}
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>

                <Typography variant="h5" sx={{ mt: 3, mb: 1.5 }}>
                  Certifications
                </Typography>
                <Stack gap={1}>
                  {data.certifications.map((certification) => (
                    <Box key={certification.id}>
                      <Typography variant="body2" fontWeight={600}>
                        {certification.name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {[certification.issuer, certification.issue_date?.slice(0, 4)]
                          .filter(Boolean)
                          .join(" · ") || "Issuer not detected"}
                      </Typography>
                    </Box>
                  ))}
                  {data.certifications.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                      None detected.
                    </Typography>
                  ) : null}
                </Stack>
              </Grid>

              <Grid item xs={12} md={6}>
                <Typography variant="h5" sx={{ mb: 1.5 }}>
                  Projects
                </Typography>
                <Stack gap={2}>
                  {data.projects.map((project) => (
                    <Box key={project.id}>
                      <Typography variant="body2" fontWeight={600}>
                        {project.name}
                      </Typography>
                      {project.description ? (
                        <Typography variant="body2" color="text.secondary">
                          {project.description}
                        </Typography>
                      ) : null}
                      {project.technologies.length ? (
                        <Stack direction="row" gap={0.5} flexWrap="wrap" sx={{ mt: 0.75 }}>
                          {project.technologies.map((tech) => (
                            <Chip key={tech} size="small" variant="outlined" label={tech} />
                          ))}
                        </Stack>
                      ) : null}
                    </Box>
                  ))}
                  {data.projects.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                      None detected.
                    </Typography>
                  ) : null}
                </Stack>
              </Grid>
            </Grid>
          ) : null}

          {tab === 3 ? (
            <Stack gap={2}>
              {can("candidate:write") ? (
                <Stack gap={1.5}>
                  <TextField
                    label="Add a recruiter note"
                    multiline
                    minRows={3}
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                  />
                  <Stack direction="row" gap={2} alignItems="center">
                    <Rating value={rating} onChange={(_event, value) => setRating(value)} />
                    <Box sx={{ flex: 1 }} />
                    <Button
                      variant="contained"
                      disabled={note.trim().length < 3 || addNote.isPending}
                      onClick={() => addNote.mutate()}
                    >
                      Save note
                    </Button>
                  </Stack>
                  <Divider />
                </Stack>
              ) : null}

              {data.notes.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  No notes yet.
                </Typography>
              ) : (
                data.notes.map((item) => (
                  <Box key={item.id}>
                    <Stack direction="row" gap={1} alignItems="center">
                      <Typography variant="subtitle2">{item.author_name ?? "Recruiter"}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {dayjs(item.created_at).format("DD MMM YYYY HH:mm")}
                      </Typography>
                      {item.is_private ? <Chip size="small" label="private" /> : null}
                      {item.rating ? <Rating size="small" value={item.rating} readOnly /> : null}
                    </Stack>
                    <Typography variant="body2" sx={{ mt: 0.5 }}>
                      {item.content}
                    </Typography>
                  </Box>
                ))
              )}
            </Stack>
          ) : null}

          {tab === 4 ? (
            similar.isLoading ? (
              <Loading label="Finding similar candidates through the graph…" />
            ) : (
              <Grid container spacing={2}>
                {(similar.data ?? []).map((item) => (
                  <Grid item xs={12} md={6} key={item.candidate_id}>
                    <Card variant="outlined">
                      <CardContent>
                        <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1}>
                          <Typography variant="h5">{item.full_name}</Typography>
                          <Chip
                            size="small"
                            color="primary"
                            label={`${item.similarity_percent}% similar`}
                          />
                        </Stack>
                        <Typography variant="body2" color="text.secondary">
                          {item.current_title ?? "Role not detected"} ·{" "}
                          {item.total_experience_years.toFixed(1)} yrs · {item.shared_skills} shared
                          skill{item.shared_skills === 1 ? "" : "s"}
                        </Typography>
                        <Stack direction="row" gap={0.5} flexWrap="wrap" sx={{ mt: 1 }}>
                          {item.shared_skill_names.slice(0, 8).map((skill) => (
                            <Chip key={skill} size="small" variant="outlined" label={skill} />
                          ))}
                          {item.shared_skill_names.length > 8 ? (
                            <Chip size="small" label={`+${item.shared_skill_names.length - 8}`} />
                          ) : null}
                        </Stack>
                        <Button
                          size="small"
                          sx={{ mt: 1.5 }}
                          onClick={() => navigate(`/candidates/${item.candidate_id}`)}
                        >
                          Open profile
                        </Button>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
                {similar.data?.length === 0 ? (
                  <Grid item xs={12}>
                    <EmptyState
                      title="No similar candidates yet"
                      description="Upload more resumes so the graph can find overlapping skill neighbourhoods."
                    />
                  </Grid>
                ) : null}
              </Grid>
            )
          ) : null}

          {tab === 5 ? (
            graph.isLoading ? (
              <Loading label="Building the candidate subgraph…" />
            ) : graph.data ? (
              <GraphCanvas view={graph.data} height={520} />
            ) : (
              <ErrorState error={graph.error} onRetry={graph.refetch} />
            )
          ) : null}

          {tab === 6 ? (
            <Stack gap={2}>
              {data.resumes.map((resume) => (
                <Card key={resume.id} variant="outlined">
                  <CardContent>
                    <Stack direction="row" justifyContent="space-between" alignItems="center" gap={2}>
                      <Box>
                        <Typography variant="subtitle2">{resume.original_filename}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          {resume.status} · {(resume.file_size / 1024).toFixed(0)} KB ·{" "}
                          {resume.page_count ?? "?"} page(s) · {resume.word_count ?? "?"} words ·{" "}
                          {resume.extraction_backend ?? "n/a"}
                          {resume.ocr_used ? " · OCR" : ""}
                        </Typography>
                      </Box>
                      <Stack direction="row" gap={1} flexShrink={0}>
                        <Button
                          size="small"
                          startIcon={<DownloadIcon />}
                          onClick={() => resumesApi.download(resume.id, resume.original_filename)}
                        >
                          Download
                        </Button>
                        {canDeleteResume ? (
                          <Button
                            size="small"
                            color="error"
                            startIcon={<DeleteOutlineIcon />}
                            disabled={deleteResume.isPending}
                            onClick={() =>
                              setResumeToDelete({
                                id: resume.id,
                                filename: resume.original_filename,
                              })
                            }
                          >
                            Delete
                          </Button>
                        ) : null}
                      </Stack>
                    </Stack>
                  </CardContent>
                </Card>
              ))}
              {data.timeline.length ? (
                <SectionCard title="Career timeline" subtitle="Extracted from the resume">
                  <Stack gap={1.5}>
                    {data.timeline.map((entry, index) => (
                      <Stack key={index} direction="row" gap={2}>
                        <Typography variant="caption" color="text.secondary" sx={{ width: 150 }}>
                          {entry.start ? dayjs(entry.start).format("MMM YYYY") : "—"} →{" "}
                          {entry.end ? dayjs(entry.end).format("MMM YYYY") : "Present"}
                        </Typography>
                        <Box>
                          <Typography variant="body2" fontWeight={600}>
                            {entry.title}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {entry.subtitle}
                          </Typography>
                        </Box>
                      </Stack>
                    ))}
                  </Stack>
                </SectionCard>
              ) : null}
            </Stack>
          ) : null}
        </CardContent>
      </Card>

      <Dialog
        open={Boolean(resumeToDelete)}
        onClose={() => (deleteResume.isPending ? undefined : setResumeToDelete(null))}
      >
        <DialogTitle>Delete resume</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Delete{" "}
            <Typography component="span" fontWeight={600}>
              {resumeToDelete?.filename}
            </Typography>
            ? The file will be removed permanently.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setResumeToDelete(null)} disabled={deleteResume.isPending}>
            Cancel
          </Button>
          <Button
            color="error"
            variant="contained"
            disabled={!resumeToDelete || deleteResume.isPending}
            onClick={() => resumeToDelete && deleteResume.mutate(resumeToDelete.id)}
          >
            Delete resume
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
