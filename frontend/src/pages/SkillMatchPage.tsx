import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Autocomplete,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Slider,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import PsychologyIcon from "@mui/icons-material/Psychology";
import { useSnackbar } from "notistack";

import { jobsApi, matchingApi, skillsApi } from "@/api/endpoints";
import { EmptyState, Loading, PageHeader, ScoreBadge, ScoreBar, SectionCard } from "@/components/common";
import type { CandidateMatch, MatchResponse, SkillEvidence } from "@/types";

const WEIGHT_KEYS = ["skill", "semantic", "experience", "certification", "project"] as const;

// Mirrors MATCH_WEIGHT_* in the backend settings, so an untouched form scores
// exactly like the API's own defaults.
const DEFAULT_WEIGHTS: Record<string, number> = {
  skill: 0.4,
  semantic: 0.2,
  experience: 0.2,
  certification: 0.1,
  project: 0.1,
};

const MATCH_TYPE_COLOR: Record<string, "success" | "info" | "warning" | "default"> = {
  exact: "success",
  synonym: "success",
  fuzzy: "info",
  related: "info",
  parent: "info",
  child: "info",
  semantic: "warning",
  graph: "warning",
};

function EvidenceChip({ evidence }: { evidence: SkillEvidence }) {
  const title = [
    evidence.matched_skill && evidence.matched_skill !== evidence.requested
      ? `matched via ${evidence.matched_skill}`
      : null,
    evidence.graph_path.length ? evidence.graph_path.join(" → ") : null,
    evidence.evidence,
    evidence.years_experience ? `${evidence.years_experience} yrs` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <Tooltip title={title || evidence.match_type}>
      <Chip
        size="small"
        label={`${evidence.requested}${evidence.mandatory ? " *" : ""}`}
        color={MATCH_TYPE_COLOR[evidence.match_type] ?? "default"}
        variant={evidence.match_type === "exact" ? "filled" : "outlined"}
      />
    </Tooltip>
  );
}

function MatchCard({ match, onOpen }: { match: CandidateMatch; onOpen: () => void }) {
  return (
    <Accordion disableGutters sx={{ borderRadius: 3, "&:before": { display: "none" }, mb: 1.5 }}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Stack direction="row" gap={2} alignItems="center" sx={{ width: "100%", pr: 2 }} flexWrap="wrap">
          <Avatar sx={{ bgcolor: "primary.main" }}>{match.rank}</Avatar>
          <Box sx={{ minWidth: 220, flex: 1 }}>
            <Typography variant="h5">{match.full_name}</Typography>
            <Typography variant="caption" color="text.secondary">
              {match.current_title ?? "—"}
              {match.current_company ? ` · ${match.current_company}` : ""} ·{" "}
              {match.total_experience_years.toFixed(1)} yrs
            </Typography>
          </Box>
          <Stack direction="row" gap={0.5} flexWrap="wrap" sx={{ flex: 1.4, minWidth: 220 }}>
            {match.matched_skills.slice(0, 6).map((evidence) => (
              <EvidenceChip key={`${evidence.requested}-m`} evidence={evidence} />
            ))}
            {match.missing_skills.slice(0, 3).map((evidence) => (
              <Chip
                key={`${evidence.requested}-x`}
                size="small"
                label={evidence.requested}
                color="error"
                variant="outlined"
              />
            ))}
          </Stack>
          <Chip
            size="small"
            label={match.recommendation}
            color={
              match.recommendation.startsWith("Highly")
                ? "success"
                : match.recommendation === "Recommended"
                  ? "info"
                  : match.recommendation === "Consider"
                    ? "warning"
                    : "default"
            }
          />
          <ScoreBadge score={match.overall_score} />
        </Stack>
      </AccordionSummary>
      <AccordionDetails>
        <Grid container spacing={3}>
          <Grid item xs={12} md={4}>
            <Stack gap={1.5}>
              <ScoreBar
                label="Skill match"
                value={match.breakdown.skill_score}
                hint={`weight ${Math.round((match.breakdown.weights.skill ?? 0) * 100)}%`}
              />
              <ScoreBar
                label="Semantic similarity"
                value={match.breakdown.semantic_score}
                hint={`weight ${Math.round((match.breakdown.weights.semantic ?? 0) * 100)}%`}
              />
              <ScoreBar
                label="Experience"
                value={match.breakdown.experience_score}
                hint={`weight ${Math.round((match.breakdown.weights.experience ?? 0) * 100)}%`}
              />
              <ScoreBar
                label="Certifications"
                value={match.breakdown.certification_score}
                hint={`weight ${Math.round((match.breakdown.weights.certification ?? 0) * 100)}%`}
              />
              <ScoreBar
                label="Projects"
                value={match.breakdown.project_score}
                hint={`weight ${Math.round((match.breakdown.weights.project ?? 0) * 100)}%`}
              />
              <Typography variant="caption" color="text.secondary">
                Confidence {Math.round(match.confidence)}%
              </Typography>
            </Stack>
          </Grid>

          <Grid item xs={12} md={8}>
            <Typography variant="h5">Why this ranking</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, whiteSpace: "pre-line" }}>
              {match.explanation}
            </Typography>

            {match.related_skills.length ? (
              <Box sx={{ mt: 2 }}>
                <Typography variant="subtitle2">Graph-expanded evidence</Typography>
                <Stack gap={0.5} sx={{ mt: 0.5 }}>
                  {match.related_skills.slice(0, 5).map((evidence) => (
                    <Typography key={evidence.requested} variant="caption" color="text.secondary">
                      {evidence.requested} ← {evidence.matched_skill}
                      {evidence.graph_path.length ? ` (${evidence.graph_path.join(" → ")})` : ""}
                    </Typography>
                  ))}
                </Stack>
              </Box>
            ) : null}

            <Grid container spacing={2} sx={{ mt: 0.5 }}>
              <Grid item xs={12} sm={6}>
                <Typography variant="subtitle2">Strengths</Typography>
                <List dense disablePadding>
                  {match.strengths.map((item) => (
                    <ListItem key={item} disableGutters>
                      <ListItemText primary={item} primaryTypographyProps={{ variant: "body2" }} />
                    </ListItem>
                  ))}
                </List>
              </Grid>
              <Grid item xs={12} sm={6}>
                <Typography variant="subtitle2">Gaps</Typography>
                <List dense disablePadding>
                  {match.gaps.map((item) => (
                    <ListItem key={item} disableGutters>
                      <ListItemText primary={item} primaryTypographyProps={{ variant: "body2" }} />
                    </ListItem>
                  ))}
                  {match.gaps.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">
                      No significant gaps.
                    </Typography>
                  ) : null}
                </List>
              </Grid>
            </Grid>

            {match.interview_questions.length ? (
              <Box sx={{ mt: 1.5 }}>
                <Typography variant="subtitle2">Suggested interview questions</Typography>
                <List dense disablePadding>
                  {match.interview_questions.map((question) => (
                    <ListItem key={question} disableGutters>
                      <ListItemText primary={question} primaryTypographyProps={{ variant: "body2" }} />
                    </ListItem>
                  ))}
                </List>
              </Box>
            ) : null}

            <Divider sx={{ my: 1.5 }} />
            <Button size="small" variant="outlined" onClick={onOpen}>
              Open full profile
            </Button>
          </Grid>
        </Grid>
      </AccordionDetails>
    </Accordion>
  );
}

export default function SkillMatchPage() {
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();

  const [requiredSkills, setRequiredSkills] = useState<string[]>([]);
  const [mandatorySkills, setMandatorySkills] = useState<string[]>([]);
  const [preferredSkills, setPreferredSkills] = useState<string[]>([]);
  const [certifications, setCertifications] = useState<string[]>([]);
  const [jobTitle, setJobTitle] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [minExperience, setMinExperience] = useState(0);
  const [topK, setTopK] = useState(20);
  const [requirementId, setRequirementId] = useState<number | "">("");
  const [weights, setWeights] = useState<Record<string, number>>(DEFAULT_WEIGHTS);
  const [response, setResponse] = useState<MatchResponse | null>(null);

  const { data: skillOptions } = useQuery({
    queryKey: ["skills", "options"],
    queryFn: () => skillsApi.list({ limit: 400 }),
    staleTime: 10 * 60_000,
  });

  const { data: requirements } = useQuery({ queryKey: ["jobs"], queryFn: () => jobsApi.list(true) });

  const run = useMutation({
    mutationFn: () =>
      matchingApi.run({
        required_skills: requiredSkills,
        mandatory_skills: mandatorySkills,
        preferred_skills: preferredSkills,
        preferred_certifications: certifications,
        min_experience_years: minExperience,
        job_title: jobTitle || null,
        job_description: jobDescription || null,
        job_requirement_id: requirementId === "" ? null : Number(requirementId),
        top_k: topK,
        weights,
      }),
    onSuccess: (data) => {
      setResponse(data);
      enqueueSnackbar(
        `Ranked ${data.returned} of ${data.total_candidates_evaluated} candidates in ${data.duration_ms} ms`,
        { variant: "success" },
      );
    },
    onError: (error: Error) => enqueueSnackbar(error.message, { variant: "error" }),
  });

  const weightTotal = Object.values(weights).reduce((sum, value) => sum + value, 0);

  return (
    <>
      <PageHeader
        title="AI skill match"
        subtitle="Graph RAG retrieval plus a weighted, explainable score across skills, semantics, experience, certifications and projects."
      />

      <Grid container spacing={2}>
        <Grid item xs={12} lg={4}>
          <Card>
            <CardContent>
              <Stack gap={2}>
                <TextField
                  select
                  label="Load a job requirement"
                  value={requirementId}
                  onChange={(event) => {
                    const value = event.target.value === "" ? "" : Number(event.target.value);
                    setRequirementId(value);
                    const requirement = requirements?.find((item) => item.id === value);
                    if (requirement) {
                      setRequiredSkills(requirement.required_skills);
                      setPreferredSkills(requirement.preferred_skills);
                      setCertifications(requirement.preferred_certifications);
                      setJobTitle(requirement.title);
                      setJobDescription(requirement.description ?? "");
                      setMinExperience(requirement.min_experience_years ?? 0);
                    }
                  }}
                >
                  <MenuItem value="">Ad-hoc criteria</MenuItem>
                  {(requirements ?? []).map((requirement) => (
                    <MenuItem key={requirement.id} value={requirement.id}>
                      {requirement.title}
                    </MenuItem>
                  ))}
                </TextField>

                <TextField
                  label="Job title"
                  value={jobTitle}
                  onChange={(event) => setJobTitle(event.target.value)}
                />

                <Autocomplete
                  multiple
                  freeSolo
                  size="small"
                  options={(skillOptions ?? []).map((skill) => skill.name)}
                  value={requiredSkills}
                  onChange={(_event, value) => setRequiredSkills(value as string[])}
                  renderInput={(params) => (
                    <TextField {...params} label="Required skills" placeholder="Python, ReactJS…" />
                  )}
                />
                <Autocomplete
                  multiple
                  freeSolo
                  size="small"
                  options={requiredSkills}
                  value={mandatorySkills}
                  onChange={(_event, value) => setMandatorySkills(value as string[])}
                  renderInput={(params) => (
                    <TextField {...params} label="Mandatory (must have)" placeholder="Subset of required" />
                  )}
                />
                <Autocomplete
                  multiple
                  freeSolo
                  size="small"
                  options={(skillOptions ?? []).map((skill) => skill.name)}
                  value={preferredSkills}
                  onChange={(_event, value) => setPreferredSkills(value as string[])}
                  renderInput={(params) => <TextField {...params} label="Preferred skills" />}
                />
                <Autocomplete
                  multiple
                  freeSolo
                  size="small"
                  options={[]}
                  value={certifications}
                  onChange={(_event, value) => setCertifications(value as string[])}
                  renderInput={(params) => <TextField {...params} label="Preferred certifications" />}
                />

                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Minimum experience: {minExperience} yrs
                  </Typography>
                  <Slider
                    value={minExperience}
                    onChange={(_event, value) => setMinExperience(value as number)}
                    min={0}
                    max={20}
                    step={0.5}
                    valueLabelDisplay="auto"
                  />
                </Box>

                <TextField
                  label="Job description (improves semantic scoring)"
                  multiline
                  minRows={3}
                  value={jobDescription}
                  onChange={(event) => setJobDescription(event.target.value)}
                />

                <Divider />
                <Typography variant="subtitle2">
                  Scoring weights{" "}
                  <Typography component="span" variant="caption" color="text.secondary">
                    (total {weightTotal.toFixed(2)})
                  </Typography>
                </Typography>
                {WEIGHT_KEYS.map((key) => (
                  <Box key={key}>
                    <Typography variant="caption" color="text.secondary" textTransform="capitalize">
                      {key}: {Math.round(weights[key] * 100)}%
                    </Typography>
                    <Slider
                      value={weights[key]}
                      onChange={(_event, value) => setWeights({ ...weights, [key]: value as number })}
                      min={0}
                      max={1}
                      step={0.05}
                      size="small"
                    />
                  </Box>
                ))}

                <TextField
                  type="number"
                  label="Results to return"
                  value={topK}
                  onChange={(event) => setTopK(Math.max(1, Math.min(200, Number(event.target.value))))}
                />

                <Button
                  variant="contained"
                  size="large"
                  startIcon={<PsychologyIcon />}
                  disabled={requiredSkills.length === 0 || run.isPending}
                  onClick={() => run.mutate()}
                >
                  {run.isPending ? "Ranking candidates…" : "Run skill match"}
                </Button>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} lg={8}>
          {run.isPending ? <Loading label="Retrieving through the knowledge graph…" height={320} /> : null}

          {!run.isPending && !response ? (
            <EmptyState
              title="Describe the role to rank candidates"
              description="Add the required skills (and optionally a job description) on the left, then run the match. Every score comes with a full breakdown and the graph path that justified it."
            />
          ) : null}

          {response ? (
            <>
              <Alert severity="info" sx={{ mb: 2 }}>
                Evaluated {response.total_candidates_evaluated} candidates in {response.duration_ms} ms ·
                embeddings: {response.embedding_model} · graph: {response.graph_backend} · reasoning:{" "}
                {response.llm_backend}
              </Alert>

              {response.results.length === 0 ? (
                <EmptyState
                  title="No candidate cleared the bar"
                  description="Try lowering the minimum experience, removing mandatory skills or broadening the required skill list."
                />
              ) : (
                response.results.map((match) => (
                  <MatchCard
                    key={match.candidate_id}
                    match={match}
                    onOpen={() => navigate(`/candidates/${match.candidate_id}`)}
                  />
                ))
              )}
            </>
          ) : null}
        </Grid>
      </Grid>

      {response?.results.length ? (
        <SectionCard title="Comparison" subtitle="Side-by-side score components for the top candidates">
          <Grid container spacing={2}>
            {response.results.slice(0, 4).map((match) => (
              <Grid item xs={12} sm={6} md={3} key={match.candidate_id}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="h5">{match.full_name}</Typography>
                    <ScoreBadge score={match.overall_score} size="small" />
                    <Stack gap={1} sx={{ mt: 1.5 }}>
                      {match.breakdown.components.map((component) => (
                        <ScoreBar
                          key={component.name}
                          label={component.name}
                          value={component.score}
                          hint={component.detail ?? undefined}
                        />
                      ))}
                    </Stack>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </SectionCard>
      ) : null}
    </>
  );
}
