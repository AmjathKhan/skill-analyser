import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  Slider,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import HubIcon from "@mui/icons-material/Hub";
import RefreshIcon from "@mui/icons-material/Refresh";
import { useSnackbar } from "notistack";
import dayjs from "dayjs";

import { graphApi, skillsApi } from "@/api/endpoints";
import GraphCanvas from "@/components/GraphCanvas";
import { ErrorState, Loading, PageHeader, SectionCard, StatCard } from "@/components/common";
import { useAuth } from "@/auth/AuthContext";

type Focus = "overview" | "skill";

export default function GraphPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { enqueueSnackbar } = useSnackbar();
  const { can } = useAuth();

  const [focus, setFocus] = useState<Focus>("overview");
  const [skill, setSkill] = useState<string | null>(null);
  const [depth, setDepth] = useState(2);
  const [limit, setLimit] = useState(220);

  const stats = useQuery({ queryKey: ["graph", "stats"], queryFn: graphApi.stats });

  const { data: skillOptions } = useQuery({
    queryKey: ["skills", "options"],
    queryFn: () => skillsApi.list({ limit: 400 }),
    staleTime: 10 * 60_000,
  });

  const view = useQuery({
    queryKey: ["graph", "view", focus, skill, depth, limit],
    queryFn: () =>
      focus === "skill" && skill ? graphApi.skill(skill, depth) : graphApi.overview(limit, 25),
  });

  const rebuild = useMutation({
    mutationFn: () => graphApi.build(true),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["graph"] });
      enqueueSnackbar(
        `Graph rebuilt: ${Number(result.nodes ?? 0)} nodes, ${Number(result.edges ?? 0)} edges in ${Number(
          result.duration_ms ?? 0,
        )} ms`,
        { variant: "success" },
      );
    },
    onError: (error: Error) => enqueueSnackbar(error.message, { variant: "error" }),
  });

  return (
    <>
      <PageHeader
        title="Knowledge graph"
        subtitle="Candidates, skills, technologies, companies, certifications and job roles connected as one traversable graph."
        actions={
          can("graph:build") ? (
            <Button
              variant="contained"
              startIcon={<RefreshIcon />}
              disabled={rebuild.isPending}
              onClick={() => rebuild.mutate()}
            >
              {rebuild.isPending ? "Rebuilding…" : "Rebuild graph"}
            </Button>
          ) : undefined
        }
      />

      <Grid container spacing={2}>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Nodes"
            value={stats.data?.node_count ?? "—"}
            hint={`backend: ${stats.data?.backend ?? "?"}`}
            icon={<HubIcon />}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard label="Relationships" value={stats.data?.edge_count ?? "—"} />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Health"
            value={stats.data?.healthy ? "Healthy" : "Degraded"}
            hint={stats.data?.detail ?? undefined}
            color={stats.data?.healthy ? "success.main" : "error.main"}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Last build"
            value={stats.data?.last_build_at ? dayjs(stats.data.last_build_at).format("DD MMM HH:mm") : "—"}
            hint={stats.data?.version ? `version ${stats.data.version}` : undefined}
          />
        </Grid>
      </Grid>

      <Card>
        <CardContent>
          <Stack direction={{ xs: "column", md: "row" }} gap={2} alignItems={{ md: "center" }}>
            <ToggleButtonGroup
              size="small"
              exclusive
              value={focus}
              onChange={(_event, value) => value && setFocus(value)}
            >
              <ToggleButton value="overview">Overview</ToggleButton>
              <ToggleButton value="skill">Focus on a skill</ToggleButton>
            </ToggleButtonGroup>

            {focus === "skill" ? (
              <Autocomplete
                size="small"
                sx={{ minWidth: 280 }}
                options={(skillOptions ?? []).map((item) => item.name)}
                value={skill}
                onChange={(_event, value) => setSkill(value)}
                renderInput={(params) => <TextField {...params} label="Skill" />}
              />
            ) : null}

            <Box sx={{ width: 200 }}>
              <Typography variant="caption" color="text.secondary">
                {focus === "skill" ? `Depth: ${depth}` : `Node limit: ${limit}`}
              </Typography>
              {focus === "skill" ? (
                <Slider value={depth} min={1} max={4} step={1} marks onChange={(_e, v) => setDepth(v as number)} />
              ) : (
                <Slider
                  value={limit}
                  min={60}
                  max={600}
                  step={20}
                  onChange={(_e, v) => setLimit(v as number)}
                />
              )}
            </Box>
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          {view.isLoading ? (
            <Loading label="Laying out the graph…" height={420} />
          ) : view.error || !view.data ? (
            <ErrorState error={view.error} onRetry={view.refetch} />
          ) : (
            <GraphCanvas
              view={view.data}
              height={600}
              onNodeClick={(node) => {
                if (node.label === "Candidate") {
                  const id = node.id.split(":").pop();
                  if (id) navigate(`/candidates/${id}`);
                } else if (node.label === "Skill") {
                  setFocus("skill");
                  setSkill(node.name);
                }
              }}
            />
          )}
        </CardContent>
      </Card>

      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <SectionCard title="Nodes by label" subtitle="Entity distribution in the graph">
            <Stack gap={1}>
              {Object.entries(stats.data?.node_counts ?? {})
                .sort((a, b) => b[1] - a[1])
                .map(([label, count]) => (
                  <Stack key={label} direction="row" justifyContent="space-between">
                    <Typography variant="body2">{label}</Typography>
                    <Chip size="small" label={count} />
                  </Stack>
                ))}
            </Stack>
          </SectionCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <SectionCard title="Relationships" subtitle="Edge types connecting the entities">
            <Stack gap={1}>
              {Object.entries(stats.data?.relationship_counts ?? {})
                .sort((a, b) => b[1] - a[1])
                .map(([relation, count]) => (
                  <Stack key={relation} direction="row" justifyContent="space-between">
                    <Typography variant="body2">{relation}</Typography>
                    <Chip size="small" label={count} />
                  </Stack>
                ))}
            </Stack>
          </SectionCard>
        </Grid>
      </Grid>
    </>
  );
}
