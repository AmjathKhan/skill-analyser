import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  InputAdornment,
  MenuItem,
  Pagination,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import SearchIcon from "@mui/icons-material/Search";
import { useSnackbar } from "notistack";

import { searchApi } from "@/api/endpoints";
import { EmptyState, Loading, PageHeader, ScoreBadge, StatusChip } from "@/components/common";
import type { SearchMode, SearchResponse } from "@/types";

const MODES: { value: SearchMode; label: string; hint: string }[] = [
  { value: "hybrid", label: "Hybrid", hint: "Keyword + semantic + graph, blended" },
  { value: "semantic", label: "Semantic", hint: "Embedding similarity over the whole profile" },
  { value: "keyword", label: "Keyword", hint: "Literal matches on name, title, company and skills" },
  { value: "graph", label: "Graph", hint: "Walks the knowledge graph from the detected skills" },
  { value: "skill", label: "Skill", hint: "Strict skill coverage with missing-skill reporting" },
];

const EXAMPLES = [
  "Python developer with 5 years experience in Django",
  "AWS certified DevOps engineer with Kubernetes",
  "React and TypeScript frontend engineer in Hyderabad",
  "NLP machine learning engineer with PyTorch and MLOps",
];

export default function SearchPage() {
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();

  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("hybrid");
  const [minExperience, setMinExperience] = useState("");
  const [location, setLocation] = useState("");
  const [sortBy, setSortBy] = useState<"ai_score" | "experience" | "upload_date" | "name">("ai_score");
  const [page, setPage] = useState(1);
  const [response, setResponse] = useState<SearchResponse | null>(null);

  const run = useMutation({
    mutationFn: (nextPage: number) =>
      searchApi.search({
        query,
        mode,
        filters: {
          min_experience: minExperience ? Number(minExperience) : null,
          location: location || null,
        },
        sort_by: sortBy,
        sort_dir: sortBy === "name" ? "asc" : "desc",
        page: nextPage,
        page_size: 10,
        include_answer: true,
      }),
    onSuccess: (data) => setResponse(data),
    onError: (error: Error) => enqueueSnackbar(error.message, { variant: "error" }),
  });

  const submit = (nextPage = 1) => {
    setPage(nextPage);
    run.mutate(nextPage);
  };

  const totalPages = response ? Math.max(1, Math.ceil(response.total / response.page_size)) : 1;

  return (
    <>
      <PageHeader
        title="Candidate search"
        subtitle="Ask in plain English. The query is parsed into skills and experience, then answered with Graph RAG retrieval."
      />

      <Card>
        <CardContent>
          <Stack gap={2}>
            <TextField
              fullWidth
              placeholder='e.g. "Senior Python developer with Kubernetes and 6 years experience"'
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") submit(1);
              }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon color="action" />
                  </InputAdornment>
                ),
                endAdornment: (
                  <InputAdornment position="end">
                    <Button variant="contained" onClick={() => submit(1)} disabled={run.isPending}>
                      Search
                    </Button>
                  </InputAdornment>
                ),
              }}
            />

            <Stack direction="row" gap={2} flexWrap="wrap" alignItems="center">
              <ToggleButtonGroup
                size="small"
                exclusive
                value={mode}
                onChange={(_event, value) => value && setMode(value)}
              >
                {MODES.map((item) => (
                  <ToggleButton key={item.value} value={item.value}>
                    <Tooltip title={item.hint}>
                      <span>{item.label}</span>
                    </Tooltip>
                  </ToggleButton>
                ))}
              </ToggleButtonGroup>

              <TextField
                size="small"
                type="number"
                label="Min experience"
                value={minExperience}
                onChange={(event) => setMinExperience(event.target.value)}
                sx={{ width: 150 }}
              />
              <TextField
                size="small"
                label="Location"
                value={location}
                onChange={(event) => setLocation(event.target.value)}
                sx={{ width: 180 }}
              />
              <TextField
                size="small"
                select
                label="Sort by"
                value={sortBy}
                onChange={(event) => setSortBy(event.target.value as typeof sortBy)}
                sx={{ width: 170 }}
              >
                <MenuItem value="ai_score">Relevance</MenuItem>
                <MenuItem value="experience">Experience</MenuItem>
                <MenuItem value="upload_date">Recently added</MenuItem>
                <MenuItem value="name">Name</MenuItem>
              </TextField>
            </Stack>

            {!response ? (
              <Stack direction="row" gap={1} flexWrap="wrap">
                {EXAMPLES.map((example) => (
                  <Chip
                    key={example}
                    label={example}
                    variant="outlined"
                    onClick={() => {
                      setQuery(example);
                      setTimeout(() => submit(1), 0);
                    }}
                  />
                ))}
              </Stack>
            ) : null}
          </Stack>
        </CardContent>
      </Card>

      {run.isPending ? <Loading label="Retrieving candidates…" /> : null}

      {response && !run.isPending ? (
        <>
          <Card>
            <CardContent>
              <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center">
                <Typography variant="body2" color="text.secondary">
                  {response.total} result(s) in {response.duration_ms} ms · mode {response.mode}
                </Typography>
                <Box sx={{ flex: 1 }} />
                {response.interpreted_skills.map((skill) => (
                  <Chip key={skill} size="small" color="primary" variant="outlined" label={skill} />
                ))}
                {response.interpreted_experience ? (
                  <Chip size="small" label={`${response.interpreted_experience}+ yrs`} />
                ) : null}
                {response.unknown_terms.slice(0, 4).map((term) => (
                  <Chip key={term} size="small" label={term} variant="outlined" />
                ))}
              </Stack>

              {response.answer ? (
                <Alert icon={<AutoAwesomeIcon />} severity="info" sx={{ mt: 2 }}>
                  <Typography variant="body2" sx={{ whiteSpace: "pre-line" }}>
                    {response.answer}
                  </Typography>
                  {response.answer_backend ? (
                    <Typography variant="caption" color="text.secondary">
                      Generated by {response.answer_backend}
                    </Typography>
                  ) : null}
                </Alert>
              ) : null}

              {response.graph_paths.length ? (
                <Box sx={{ mt: 1.5 }}>
                  <Typography variant="caption" color="text.secondary">
                    Graph paths used: {response.graph_paths.slice(0, 6).join(" | ")}
                  </Typography>
                </Box>
              ) : null}
            </CardContent>
          </Card>

          {response.items.length === 0 ? (
            <EmptyState
              title="No candidates matched"
              description="Try the hybrid mode, drop the location filter or lower the minimum experience."
            />
          ) : (
            <Stack gap={1.5}>
              {response.items.map((hit) => (
                <Card key={hit.candidate_id} sx={{ cursor: "pointer" }}>
                  <CardContent onClick={() => navigate(`/candidates/${hit.candidate_id}`)}>
                    <Grid container spacing={2} alignItems="center">
                      <Grid item xs={12} md={4}>
                        <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
                          <Typography variant="h5">{hit.full_name}</Typography>
                          <StatusChip status={hit.status} />
                        </Stack>
                        <Typography variant="body2" color="text.secondary">
                          {hit.current_title ?? "—"}
                          {hit.current_company ? ` · ${hit.current_company}` : ""}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {hit.total_experience_years.toFixed(1)} yrs
                          {hit.location ? ` · ${hit.location}` : ""}
                          {hit.highest_degree ? ` · ${hit.highest_degree}` : ""}
                        </Typography>
                      </Grid>

                      <Grid item xs={12} md={5}>
                        <Stack direction="row" gap={0.5} flexWrap="wrap">
                          {hit.matched_skills.slice(0, 8).map((skill) => (
                            <Tooltip
                              key={skill.skill}
                              title={`${skill.match_type} · ${Math.round(skill.score * 100)}%`}
                            >
                              <Chip size="small" color="success" variant="outlined" label={skill.skill} />
                            </Tooltip>
                          ))}
                          {hit.missing_skills.slice(0, 4).map((skill) => (
                            <Chip key={skill} size="small" color="error" variant="outlined" label={skill} />
                          ))}
                        </Stack>
                        {hit.snippet ? (
                          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                            {hit.snippet}
                          </Typography>
                        ) : null}
                      </Grid>

                      <Grid item xs={12} md={3}>
                        <Stack direction="row" gap={1} alignItems="center" justifyContent="flex-end">
                          <ScoreBadge score={hit.ai_score} />
                        </Stack>
                        <Stack direction="row" gap={0.5} justifyContent="flex-end" sx={{ mt: 0.75 }}>
                          {hit.channels.map((channel) => (
                            <Chip key={channel} size="small" label={channel} />
                          ))}
                        </Stack>
                        <Typography
                          variant="caption"
                          color="text.secondary"
                          sx={{ display: "block", textAlign: "right", mt: 0.5 }}
                        >
                          kw {Math.round(hit.keyword_score)} · sem {Math.round(hit.semantic_score)} · graph{" "}
                          {Math.round(hit.graph_score)}
                        </Typography>
                      </Grid>
                    </Grid>
                  </CardContent>
                </Card>
              ))}

              <Divider />
              <Stack alignItems="center">
                <Pagination
                  page={page}
                  count={totalPages}
                  onChange={(_event, value) => submit(value)}
                  color="primary"
                />
              </Stack>
            </Stack>
          )}
        </>
      ) : null}
    </>
  );
}
