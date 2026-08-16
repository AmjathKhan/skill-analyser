import { useMemo, useState, type ReactElement, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  LinearProgress,
  List,
  ListItemButton,
  ListItemText,
  MenuItem,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";
import AssessmentIcon from "@mui/icons-material/Assessment";
import GroupsIcon from "@mui/icons-material/Groups";
import HowToRegIcon from "@mui/icons-material/HowToReg";
import HubIcon from "@mui/icons-material/Hub";
import PictureAsPdfIcon from "@mui/icons-material/PictureAsPdf";
import PsychologyIcon from "@mui/icons-material/Psychology";
import SchoolIcon from "@mui/icons-material/School";
import TableViewIcon from "@mui/icons-material/TableView";
import GridOnIcon from "@mui/icons-material/GridOn";
import WorkIcon from "@mui/icons-material/Work";
import dayjs from "dayjs";
import { useSnackbar } from "notistack";

import { reportsApi, skillsApi } from "@/api/endpoints";
import { CardsSkeleton, EmptyState, ErrorState, PageHeader, ScoreBadge, SectionCard, StatCard } from "@/components/common";
import type { NamedValue, ReportInsight, ReportResponse, SkillGapItem } from "@/types";

const COLORS = ["#1a73e8", "#12b76a", "#f79009", "#e11d48", "#7c4dff", "#06b6d4", "#64748b", "#0891b2"];

const INSIGHT_SEVERITY: Record<string, "success" | "info" | "warning" | "error"> = {
  success: "success",
  info: "info",
  warning: "warning",
  error: "error",
};

function asList<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function normalizeReport(raw: ReportResponse): ReportResponse {
  const kpis = raw?.kpis ?? ({} as ReportResponse["kpis"]);
  return {
    generated_at: raw?.generated_at ?? new Date().toISOString(),
    period_start: raw?.period_start ?? null,
    period_end: raw?.period_end ?? null,
    kpis: {
      total_candidates: asNumber(kpis.total_candidates),
      resumes_processed: asNumber(kpis.resumes_processed),
      parse_success_rate: asNumber(kpis.parse_success_rate),
      average_parse_ms: asNumber(kpis.average_parse_ms),
      shortlist_rate: asNumber(kpis.shortlist_rate),
      rejection_rate: asNumber(kpis.rejection_rate),
      hired: asNumber(kpis.hired),
      interviewing: asNumber(kpis.interviewing),
      pending_review: asNumber(kpis.pending_review),
      failed_resumes: asNumber(kpis.failed_resumes),
      average_experience_years: asNumber(kpis.average_experience_years),
      skills_per_candidate: asNumber(kpis.skills_per_candidate),
      taxonomy_coverage_percent: asNumber(kpis.taxonomy_coverage_percent),
      unique_skills: asNumber(kpis.unique_skills),
      unique_companies: asNumber(kpis.unique_companies),
      new_candidates_in_period: asNumber(kpis.new_candidates_in_period),
      matches_run: asNumber(kpis.matches_run),
      average_match_score: typeof kpis.average_match_score === "number" ? kpis.average_match_score : null,
    },
    insights: asList(raw?.insights),
    top_technologies: asList(raw?.top_technologies),
    top_skills: asList(raw?.top_skills),
    top_categories: asList(raw?.top_categories),
    hiring_trends: asList(raw?.hiring_trends),
    skill_gaps: asList(raw?.skill_gaps).map((gap) => ({
      ...gap,
      suggested_learning: asList(gap.suggested_learning),
    })),
    pipeline: asList(raw?.pipeline),
    experience_distribution: asList(raw?.experience_distribution),
    top_companies: asList(raw?.top_companies),
    top_certifications: asList(raw?.top_certifications),
    top_locations: asList(raw?.top_locations),
    education_distribution: asList(raw?.education_distribution),
    recent_matches: asList(raw?.recent_matches).map((run) => ({
      ...run,
      top_candidates: asList(run.top_candidates),
    })),
  };
}

function ChartFrame({ children, empty }: { children: ReactNode; empty?: boolean }) {
  if (empty) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ py: 6, textAlign: "center" }}>
        No data for this chart in the selected period.
      </Typography>
    );
  }
  return (
    <Box sx={{ width: "100%", height: 300 }}>
      <ResponsiveContainer>{children as ReactElement}</ResponsiveContainer>
    </Box>
  );
}

function RankTable({ rows, valueLabel = "Candidates" }: { rows: NamedValue[]; valueLabel?: string }) {
  const max = Math.max(1, ...rows.map((row) => row.value));
  return (
    <Stack gap={1.25}>
      {rows.map((row, index) => (
        <Box key={row.name}>
          <Stack direction="row" justifyContent="space-between" gap={1}>
            <Typography variant="body2" noWrap title={row.name}>
              {index + 1}. {row.name}
              {row.extra ? (
                <Typography component="span" variant="caption" color="text.secondary">
                  {` · ${row.extra}`}
                </Typography>
              ) : null}
            </Typography>
            <Typography variant="body2" fontWeight={600}>
              {row.value} {valueLabel === "Candidates" ? "" : valueLabel}
            </Typography>
          </Stack>
          <LinearProgress
            variant="determinate"
            value={Math.min(100, (100 * row.value) / max)}
            sx={{ height: 6, borderRadius: 4, mt: 0.5 }}
          />
        </Box>
      ))}
    </Stack>
  );
}

export default function ReportsPage() {
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();
  const [months, setMonths] = useState(6);
  const [gapSkills, setGapSkills] = useState<string[]>([]);
  const [tab, setTab] = useState(0);
  const [exporting, setExporting] = useState<string | null>(null);

  const { data: skillOptions } = useQuery({
    queryKey: ["skills", "options"],
    queryFn: () => skillsApi.list({ limit: 400 }),
    staleTime: 10 * 60_000,
  });

  const report = useQuery({
    queryKey: ["reports", months, gapSkills],
    queryFn: async () =>
      normalizeReport(
        await reportsApi.get({ months, gap_skills: gapSkills.length ? gapSkills : undefined }),
      ),
    placeholderData: keepPreviousData,
  });

  const data = report.data ? normalizeReport(report.data) : undefined;
  const kpis = data?.kpis;

  const pipelineChart = useMemo(
    () => (data?.pipeline ?? []).filter((stage) => stage.count > 0 || ["new", "shortlisted", "hired"].includes(stage.status)),
    [data?.pipeline],
  );

  const conversions = useMemo(() => {
    const stages = (data?.pipeline ?? []).filter((stage) => stage.count > 0);
    return stages.slice(0, -1).map((stage, index) => {
      const next = stages[index + 1];
      const rate = stage.count ? Math.round((100 * next.count) / stage.count) : 0;
      return { from: stage.label, to: next.label, fromCount: stage.count, toCount: next.count, rate };
    });
  }, [data?.pipeline]);

  const download = async (format: "pdf" | "csv" | "excel") => {
    setExporting(format);
    try {
      await reportsApi.export(format, months, gapSkills);
      enqueueSnackbar(`Downloaded ${format.toUpperCase()} report`, { variant: "success" });
    } catch (error) {
      enqueueSnackbar(error instanceof Error ? error.message : "Export failed", { variant: "error" });
    } finally {
      setExporting(null);
    }
  };

  if (report.isLoading && !data) {
    return (
      <>
        <PageHeader title="Reports & analytics" subtitle="Loading recruitment metrics…" />
        <CardsSkeleton count={4} />
      </>
    );
  }
  if ((report.error && !data) || !kpis || !data) {
    return <ErrorState error={report.error} onRetry={report.refetch} />;
  }

  const periodLabel =
    data.period_start && data.period_end
      ? `${dayjs(data.period_start).format("DD MMM YYYY")} – ${dayjs(data.period_end).format("DD MMM YYYY")}`
      : `Last ${months} months`;

  return (
    <>
      <PageHeader
        title="Reports & analytics"
        subtitle={`Generated ${dayjs(data.generated_at).format("DD MMM YYYY HH:mm")} · ${periodLabel}`}
        actions={
          <>
            <Button
              variant="outlined"
              startIcon={<PictureAsPdfIcon />}
              disabled={Boolean(exporting)}
              onClick={() => void download("pdf")}
            >
              {exporting === "pdf" ? "Exporting…" : "PDF"}
            </Button>
            <Button
              variant="outlined"
              startIcon={<TableViewIcon />}
              disabled={Boolean(exporting)}
              onClick={() => void download("csv")}
            >
              CSV
            </Button>
            <Button
              variant="outlined"
              startIcon={<GridOnIcon />}
              disabled={Boolean(exporting)}
              onClick={() => void download("excel")}
            >
              Excel
            </Button>
          </>
        }
      />

      {report.isFetching ? <LinearProgress sx={{ borderRadius: 1 }} /> : null}

      <Card>
        <CardContent>
          <Stack direction={{ xs: "column", md: "row" }} gap={2} alignItems={{ md: "center" }}>
            <TextField
              select
              size="small"
              label="Period"
              value={months}
              onChange={(event) => setMonths(Number(event.target.value))}
              sx={{ minWidth: 180 }}
            >
              {[3, 6, 12, 18, 24].map((value) => (
                <MenuItem key={value} value={value}>
                  Last {value} months
                </MenuItem>
              ))}
            </TextField>
            <Autocomplete
              multiple
              size="small"
              sx={{ flex: 1 }}
              options={(skillOptions ?? []).map((skill) => skill.name)}
              value={gapSkills}
              onChange={(_event, value) => setGapSkills(value)}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Skill gap analysis"
                  placeholder="Leave empty to analyse the 10 most common skills"
                />
              )}
            />
          </Stack>
        </CardContent>
        <Tabs
          value={tab}
          onChange={(_event, value) => setTab(value)}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ px: 2, borderTop: "1px solid", borderColor: "divider" }}
        >
          <Tab label="Overview" />
          <Tab label="Pipeline & trends" />
          <Tab label="Skills & gaps" />
          <Tab label="Talent sources" />
          <Tab label={`Match runs (${data.recent_matches.length})`} />
        </Tabs>
      </Card>

      {tab === 0 ? <OverviewTab data={data} /> : null}
      {tab === 1 ? (
        <PipelineTab data={data} pipelineChart={pipelineChart} conversions={conversions} />
      ) : null}
      {tab === 2 ? <SkillsTab data={data} /> : null}
      {tab === 3 ? <SourcesTab data={data} /> : null}
      {tab === 4 ? <MatchesTab data={data} onOpenCandidate={(id) => navigate(`/candidates/${id}`)} /> : null}
    </>
  );
}

function OverviewTab({ data }: { data: ReportResponse }) {
  const { kpis } = data;
  return (
    <>
      <Grid container spacing={2}>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Total candidates"
            value={kpis.total_candidates}
            hint={`${kpis.new_candidates_in_period} added in this period`}
            icon={<GroupsIcon />}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Shortlist rate"
            value={`${kpis.shortlist_rate.toFixed(1)}%`}
            hint={`${kpis.hired} hired · ${kpis.interviewing} interviewing`}
            icon={<HowToRegIcon />}
            color="success.main"
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Skills mapped"
            value={kpis.unique_skills}
            hint={`${kpis.taxonomy_coverage_percent.toFixed(1)}% taxonomy coverage`}
            icon={<HubIcon />}
            color="secondary.main"
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Match runs"
            value={kpis.matches_run}
            hint={
              kpis.average_match_score != null
                ? `avg score ${kpis.average_match_score.toFixed(1)}%`
                : `${kpis.skills_per_candidate.toFixed(1)} skills / candidate`
            }
            icon={<PsychologyIcon />}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Resumes processed"
            value={kpis.resumes_processed}
            hint={`${kpis.parse_success_rate.toFixed(1)}% success · ${Math.round(kpis.average_parse_ms)} ms`}
            icon={<AssessmentIcon />}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Pending review"
            value={kpis.pending_review}
            hint={`${kpis.rejection_rate.toFixed(1)}% rejected · ${kpis.failed_resumes} failed parses`}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Avg experience"
            value={`${kpis.average_experience_years.toFixed(1)} yrs`}
            hint={`${kpis.unique_companies} companies in work history`}
            icon={<WorkIcon />}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard
            label="Skills / candidate"
            value={kpis.skills_per_candidate.toFixed(1)}
            hint="Normalized mentions per profile"
            icon={<SchoolIcon />}
          />
        </Grid>
      </Grid>

      {data.insights.length ? (
        <Grid container spacing={2}>
          {data.insights.map((insight) => (
            <Grid item xs={12} md={6} key={insight.title}>
              <InsightAlert insight={insight} />
            </Grid>
          ))}
        </Grid>
      ) : null}

      <Grid container spacing={2}>
        <Grid item xs={12} lg={8}>
          <SectionCard title="Hiring trends" subtitle="Uploads, new candidates, shortlists and rejections">
            <ChartFrame empty={!data.hiring_trends.length}>
              <ComposedChart data={data.hiring_trends}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
                <XAxis dataKey="period" fontSize={12} />
                <YAxis fontSize={12} allowDecimals={false} />
                <ChartTooltip />
                <Legend />
                <Area type="monotone" dataKey="candidates" name="New candidates" fill="#7c4dff33" stroke="#7c4dff" strokeWidth={2} />
                <Area type="monotone" dataKey="uploads" name="Uploads" fill="#1a73e833" stroke="#1a73e8" strokeWidth={2} />
                <Line type="monotone" dataKey="shortlisted" name="Shortlisted" stroke="#12b76a" strokeWidth={2} />
                <Line type="monotone" dataKey="rejected" name="Rejected" stroke="#e11d48" strokeWidth={2} />
              </ComposedChart>
            </ChartFrame>
          </SectionCard>
        </Grid>
        <Grid item xs={12} lg={4}>
          <SectionCard title="Pipeline mix" subtitle="Share of candidates by status">
            <ChartFrame empty={!data.pipeline.some((stage) => stage.count)}>
              <PieChart>
                <Pie data={data.pipeline.filter((stage) => stage.count > 0)} dataKey="count" nameKey="label" innerRadius={55} outerRadius={100} paddingAngle={2}>
                  {data.pipeline
                    .filter((stage) => stage.count > 0)
                    .map((stage, index) => (
                      <Cell key={stage.status} fill={COLORS[index % COLORS.length]} />
                    ))}
                </Pie>
                <ChartTooltip />
                <Legend />
              </PieChart>
            </ChartFrame>
          </SectionCard>
        </Grid>
      </Grid>
    </>
  );
}

function InsightAlert({ insight }: { insight: ReportInsight }) {
  return (
    <Alert severity={INSIGHT_SEVERITY[insight.level] ?? "info"} sx={{ height: "100%" }}>
      <Typography variant="subtitle2">{insight.title}</Typography>
      <Typography variant="body2">{insight.detail}</Typography>
    </Alert>
  );
}

function PipelineTab({
  data,
  pipelineChart,
  conversions,
}: {
  data: ReportResponse;
  pipelineChart: ReportResponse["pipeline"];
  conversions: { from: string; to: string; fromCount: number; toCount: number; rate: number }[];
}) {
  return (
    <Grid container spacing={2}>
      <Grid item xs={12} lg={7}>
        <SectionCard title="Pipeline volume" subtitle="Candidates currently in each stage">
          <ChartFrame empty={!pipelineChart.length}>
            <BarChart data={pipelineChart} layout="vertical" margin={{ left: 24 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
              <XAxis type="number" fontSize={12} allowDecimals={false} />
              <YAxis type="category" dataKey="label" width={120} fontSize={12} />
              <ChartTooltip />
              <Bar dataKey="count" name="Candidates" radius={[0, 6, 6, 0]}>
                {pipelineChart.map((stage, index) => (
                  <Cell key={stage.status} fill={COLORS[index % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ChartFrame>
        </SectionCard>
      </Grid>
      <Grid item xs={12} lg={5}>
        <SectionCard title="Stage conversion" subtitle="Share moving from one populated stage to the next">
          {conversions.length ? (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>From → To</TableCell>
                  <TableCell align="right">Volume</TableCell>
                  <TableCell align="right">Conversion</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {conversions.map((row) => (
                  <TableRow key={`${row.from}-${row.to}`}>
                    <TableCell>
                      {row.from} → {row.to}
                    </TableCell>
                    <TableCell align="right">
                      {row.fromCount} → {row.toCount}
                    </TableCell>
                    <TableCell align="right">{row.rate}%</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
              Move candidates through stages to see conversion between them.
            </Typography>
          )}
        </SectionCard>
      </Grid>
      <Grid item xs={12} md={6}>
        <SectionCard title="Experience mix" subtitle="Seniority of the current pool">
          <ChartFrame empty={!data.experience_distribution.some((item) => item.value)}>
            <BarChart data={data.experience_distribution}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
              <XAxis dataKey="name" fontSize={12} />
              <YAxis fontSize={12} allowDecimals={false} />
              <ChartTooltip />
              <Bar dataKey="value" name="Candidates" fill="#1a73e8" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ChartFrame>
        </SectionCard>
      </Grid>
      <Grid item xs={12} md={6}>
        <SectionCard title="Monthly movement" subtitle="Shortlists vs rejections">
          <ChartFrame empty={!data.hiring_trends.length}>
            <BarChart data={data.hiring_trends}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
              <XAxis dataKey="period" fontSize={12} />
              <YAxis fontSize={12} allowDecimals={false} />
              <ChartTooltip />
              <Legend />
              <Bar dataKey="shortlisted" name="Shortlisted" fill="#12b76a" radius={[4, 4, 0, 0]} />
              <Bar dataKey="rejected" name="Rejected" fill="#e11d48" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ChartFrame>
        </SectionCard>
      </Grid>
    </Grid>
  );
}

function SkillsTab({ data }: { data: ReportResponse }) {
  const gaps: SkillGapItem[] = data.skill_gaps;
  return (
    <Grid container spacing={2}>
      <Grid item xs={12} lg={7}>
        <SectionCard title="Top skills in the pool" subtitle="Normalized against the knowledge base">
          <ChartFrame empty={!data.top_skills.length}>
            <BarChart data={data.top_skills.slice(0, 12)} layout="vertical" margin={{ left: 16 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
              <XAxis type="number" fontSize={12} allowDecimals={false} />
              <YAxis type="category" dataKey="name" width={130} fontSize={12} />
              <ChartTooltip />
              <Bar dataKey="value" name="Candidates" fill="#1a73e8" radius={[0, 6, 6, 0]} />
            </BarChart>
          </ChartFrame>
        </SectionCard>
      </Grid>
      <Grid item xs={12} lg={5}>
        <SectionCard title="Skill categories" subtitle="Where the talent is concentrated">
          <ChartFrame empty={!data.top_categories.length}>
            <BarChart data={data.top_categories.slice(0, 10)} layout="vertical" margin={{ left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
              <XAxis type="number" fontSize={12} allowDecimals={false} />
              <YAxis type="category" dataKey="name" width={140} fontSize={12} />
              <ChartTooltip />
              <Bar dataKey="value" name="Candidates" fill="#7c4dff" radius={[0, 6, 6, 0]} />
            </BarChart>
          </ChartFrame>
        </SectionCard>
      </Grid>
      <Grid item xs={12} md={6}>
        <SectionCard title="Technology stacks" subtitle="Across parsed resumes">
          {data.top_technologies.length ? (
            <RankTable rows={data.top_technologies} />
          ) : (
            <Typography variant="body2" color="text.secondary">
              No technology-stack tags yet.
            </Typography>
          )}
        </SectionCard>
      </Grid>
      <Grid item xs={12} md={6}>
        <SectionCard
          title="Skill coverage"
          subtitle="How much of the pool has each analysed skill — pick skills above to focus"
        >
          <ChartFrame empty={!gaps.length}>
            <BarChart data={gaps.slice(0, 12)} layout="vertical" margin={{ left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
              <XAxis type="number" domain={[0, 100]} unit="%" fontSize={12} />
              <YAxis type="category" dataKey="skill" width={120} fontSize={12} />
              <ChartTooltip formatter={(value) => [`${Number(value).toFixed(1)}%`, "Coverage"]} />
              <Bar dataKey="coverage_percent" name="Coverage" fill="#0ea5e9" radius={[0, 6, 6, 0]} />
            </BarChart>
          </ChartFrame>
        </SectionCard>
      </Grid>
      <Grid item xs={12}>
        <SectionCard title="Skill gap analysis" subtitle="Low coverage means the skill is scarce — suggested related skills can bridge the gap">
          {gaps.length ? (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Skill</TableCell>
                  <TableCell>Category</TableCell>
                  <TableCell align="right">Candidates</TableCell>
                  <TableCell sx={{ minWidth: 160 }}>Coverage</TableCell>
                  <TableCell align="right">Demand</TableCell>
                  <TableCell>Suggested learning</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {gaps.map((gap) => (
                  <TableRow key={gap.skill} hover>
                    <TableCell>{gap.skill}</TableCell>
                    <TableCell>{gap.category ?? "—"}</TableCell>
                    <TableCell align="right">{gap.candidates_with_skill}</TableCell>
                    <TableCell>
                      <Stack direction="row" alignItems="center" gap={1}>
                        <LinearProgress
                          variant="determinate"
                          value={Math.min(100, gap.coverage_percent)}
                          sx={{ flex: 1, height: 7, borderRadius: 4 }}
                          color={gap.coverage_percent < 25 ? "error" : gap.coverage_percent < 50 ? "warning" : "success"}
                        />
                        <Typography variant="caption" sx={{ minWidth: 40 }}>
                          {gap.coverage_percent.toFixed(0)}%
                        </Typography>
                      </Stack>
                    </TableCell>
                    <TableCell align="right">{gap.demand_score.toFixed(0)}</TableCell>
                    <TableCell>
                      <Stack direction="row" gap={0.5} flexWrap="wrap">
                        {gap.suggested_learning.map((item) => (
                          <Chip key={item} size="small" variant="outlined" label={item} />
                        ))}
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <EmptyState title="No skill gaps yet" description="Upload resumes or pick skills in the filter above." />
          )}
        </SectionCard>
      </Grid>
    </Grid>
  );
}

function SourcesTab({ data }: { data: ReportResponse }) {
  return (
    <Grid container spacing={2}>
      <Grid item xs={12} md={6}>
        <SectionCard title="Companies" subtitle="Where candidates have worked">
          {data.top_companies.length ? (
            <ChartFrame>
              <BarChart data={data.top_companies.slice(0, 10)} layout="vertical" margin={{ left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
                <XAxis type="number" fontSize={12} allowDecimals={false} />
                <YAxis type="category" dataKey="name" width={140} fontSize={12} />
                <ChartTooltip />
                <Bar dataKey="value" name="Candidates" fill="#f79009" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ChartFrame>
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
              No company history parsed yet.
            </Typography>
          )}
        </SectionCard>
      </Grid>
      <Grid item xs={12} md={6}>
        <SectionCard title="Locations" subtitle="City, country or listed location">
          {data.top_locations.length ? (
            <RankTable rows={data.top_locations} />
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
              No locations parsed yet.
            </Typography>
          )}
        </SectionCard>
      </Grid>
      <Grid item xs={12} md={6}>
        <SectionCard title="Education" subtitle="Highest degree on the profile">
          {data.education_distribution.length ? (
            <ChartFrame>
              <PieChart>
                <Pie data={data.education_distribution} dataKey="value" nameKey="name" innerRadius={50} outerRadius={100} paddingAngle={2}>
                  {data.education_distribution.map((item, index) => (
                    <Cell key={item.name} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <ChartTooltip />
                <Legend />
              </PieChart>
            </ChartFrame>
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
              No education data yet.
            </Typography>
          )}
        </SectionCard>
      </Grid>
      <Grid item xs={12} md={6}>
        <SectionCard title="Certifications" subtitle="Most frequent credentials">
          {data.top_certifications.length ? (
            <RankTable rows={data.top_certifications} />
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
              No certifications parsed yet.
            </Typography>
          )}
        </SectionCard>
      </Grid>
    </Grid>
  );
}

function MatchesTab({
  data,
  onOpenCandidate,
}: {
  data: ReportResponse;
  onOpenCandidate: (id: number) => void;
}) {
  if (!data.recent_matches.length) {
    return (
      <EmptyState
        title="No match runs yet"
        description="Run AI skill match from a job requirement to see ranked shortlists here."
      />
    );
  }
  return (
    <Grid container spacing={2}>
      {data.recent_matches.map((run) => (
        <Grid item xs={12} md={6} key={run.run_id}>
          <SectionCard
            title={run.title || `Match run #${run.run_id}`}
            subtitle={`${dayjs(run.created_at).format("DD MMM YYYY HH:mm")}${run.created_by ? ` · ${run.created_by}` : ""} · ${run.candidates_evaluated} evaluated`}
            action={run.top_score != null ? <ScoreBadge score={run.top_score} size="small" /> : undefined}
          >
            <List dense disablePadding>
              {run.top_candidates.map((candidate, index) => (
                <ListItemButton key={candidate.candidate_id} onClick={() => onOpenCandidate(candidate.candidate_id)}>
                  <ListItemText
                    primary={`${index + 1}. ${candidate.name}`}
                    secondary={candidate.recommendation ?? undefined}
                  />
                  <ScoreBadge score={candidate.score} size="small" />
                </ListItemButton>
              ))}
            </List>
          </SectionCard>
        </Grid>
      ))}
    </Grid>
  );
}
