import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  LinearProgress,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";
import PictureAsPdfIcon from "@mui/icons-material/PictureAsPdf";
import TableViewIcon from "@mui/icons-material/TableView";
import GridOnIcon from "@mui/icons-material/GridOn";
import dayjs from "dayjs";

import { reportsApi, skillsApi } from "@/api/endpoints";
import { CardsSkeleton, ErrorState, PageHeader, SectionCard, StatCard } from "@/components/common";

const COLORS = ["#1a73e8", "#12b76a", "#f79009", "#e11d48", "#7c4dff", "#06b6d4", "#64748b", "#0891b2"];

export default function ReportsPage() {
  const [months, setMonths] = useState(6);
  const [gapSkills, setGapSkills] = useState<string[]>([]);

  const { data: skillOptions } = useQuery({
    queryKey: ["skills", "options"],
    queryFn: () => skillsApi.list({ limit: 400 }),
    staleTime: 10 * 60_000,
  });

  const report = useQuery({
    queryKey: ["reports", months, gapSkills],
    queryFn: () => reportsApi.get({ months, gap_skills: gapSkills.length ? gapSkills : undefined }),
  });

  if (report.isLoading) return <CardsSkeleton count={4} />;
  if (report.error || !report.data) return <ErrorState error={report.error} onRetry={report.refetch} />;

  const data = report.data;
  const kpis = data.kpis;

  return (
    <>
      <PageHeader
        title="Reports & analytics"
        subtitle={`Generated ${dayjs(data.generated_at).format("DD MMM YYYY HH:mm")}${
          data.period_start ? ` · period from ${dayjs(data.period_start).format("DD MMM YYYY")}` : ""
        }`}
        actions={
          <>
            <Button
              variant="outlined"
              startIcon={<PictureAsPdfIcon />}
              onClick={() => reportsApi.export("pdf", months)}
            >
              PDF
            </Button>
            <Button
              variant="outlined"
              startIcon={<TableViewIcon />}
              onClick={() => reportsApi.export("csv", months)}
            >
              CSV
            </Button>
            <Button
              variant="outlined"
              startIcon={<GridOnIcon />}
              onClick={() => reportsApi.export("excel", months)}
            >
              Excel
            </Button>
          </>
        }
      />

      <Card>
        <CardContent>
          <Stack direction={{ xs: "column", md: "row" }} gap={2}>
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
                <TextField {...params} label="Skill gap analysis" placeholder="Pick skills to analyse" />
              )}
            />
          </Stack>
        </CardContent>
      </Card>

      <Grid container spacing={2}>
        {[
          { label: "Total candidates", value: kpis.total_candidates },
          { label: "Resumes processed", value: kpis.resumes_processed },
          { label: "Parse success", value: `${kpis.parse_success_rate.toFixed(1)}%`, hint: `${Math.round(kpis.average_parse_ms)} ms avg` },
          { label: "Shortlist rate", value: `${kpis.shortlist_rate.toFixed(1)}%`, hint: `rejection ${kpis.rejection_rate.toFixed(1)}%` },
          { label: "Avg experience", value: `${kpis.average_experience_years.toFixed(1)} yrs` },
          { label: "Skills / candidate", value: kpis.skills_per_candidate.toFixed(1) },
          { label: "Taxonomy coverage", value: `${kpis.taxonomy_coverage_percent.toFixed(1)}%` },
          {
            label: "Match runs",
            value: kpis.matches_run,
            hint: kpis.average_match_score != null ? `avg score ${kpis.average_match_score.toFixed(1)}%` : undefined,
          },
        ].map((card) => (
          <Grid item xs={6} md={3} key={card.label}>
            <StatCard label={card.label} value={card.value} hint={card.hint} />
          </Grid>
        ))}
      </Grid>

      <Grid container spacing={2}>
        <Grid item xs={12} lg={8}>
          <SectionCard title="Hiring trends" subtitle="Uploads, new candidates, shortlists and rejections">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={data.hiring_trends}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
                <XAxis dataKey="period" fontSize={12} />
                <YAxis fontSize={12} allowDecimals={false} />
                <ChartTooltip />
                <Legend />
                <Line type="monotone" dataKey="uploads" stroke="#1a73e8" strokeWidth={2} />
                <Line type="monotone" dataKey="candidates" stroke="#7c4dff" strokeWidth={2} />
                <Line type="monotone" dataKey="shortlisted" stroke="#12b76a" strokeWidth={2} />
                <Line type="monotone" dataKey="rejected" stroke="#e11d48" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </SectionCard>
        </Grid>

        <Grid item xs={12} lg={4}>
          <SectionCard title="Pipeline" subtitle="Candidate distribution by status">
            <Stack gap={1.5}>
              {data.pipeline.map((stage) => (
                <Box key={stage.status}>
                  <Stack direction="row" justifyContent="space-between">
                    <Typography variant="body2">{stage.label}</Typography>
                    <Typography variant="body2" fontWeight={600}>
                      {stage.count} · {stage.percent.toFixed(0)}%
                    </Typography>
                  </Stack>
                  <LinearProgress
                    variant="determinate"
                    value={Math.min(100, stage.percent)}
                    sx={{ height: 7, borderRadius: 5, mt: 0.5 }}
                  />
                </Box>
              ))}
            </Stack>
          </SectionCard>
        </Grid>

        <Grid item xs={12} md={6}>
          <SectionCard title="Top technologies" subtitle="Across all parsed resumes">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={data.top_technologies.slice(0, 10)} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
                <XAxis type="number" fontSize={12} allowDecimals={false} />
                <YAxis type="category" dataKey="name" width={120} fontSize={12} />
                <ChartTooltip />
                <Bar dataKey="value" fill="#1a73e8" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </SectionCard>
        </Grid>

        <Grid item xs={12} md={6}>
          <SectionCard title="Experience distribution" subtitle="Candidate seniority mix">
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={data.experience_distribution}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={60}
                  outerRadius={110}
                  paddingAngle={2}
                >
                  {data.experience_distribution.map((_entry, index) => (
                    <Cell key={index} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <ChartTooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </SectionCard>
        </Grid>

        <Grid item xs={12} md={6}>
          <SectionCard title="Top skills" subtitle="Normalized against the knowledge base">
            <Stack direction="row" gap={1} flexWrap="wrap">
              {data.top_skills.slice(0, 30).map((skill) => (
                <Chip key={skill.name} label={`${skill.name} · ${skill.value}`} variant="outlined" />
              ))}
            </Stack>
          </SectionCard>
        </Grid>

        <Grid item xs={12} md={6}>
          <SectionCard title="Top companies" subtitle="Where candidates come from">
            <Table size="small">
              <TableBody>
                {data.top_companies.slice(0, 10).map((company) => (
                  <TableRow key={company.name}>
                    <TableCell>{company.name}</TableCell>
                    <TableCell align="right">{company.value}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </SectionCard>
        </Grid>

        {data.skill_gaps.length ? (
          <Grid item xs={12}>
            <SectionCard
              title="Skill gap analysis"
              subtitle="Coverage of the selected skills across the candidate pool"
            >
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Skill</TableCell>
                    <TableCell>Category</TableCell>
                    <TableCell align="right">Candidates</TableCell>
                    <TableCell align="right">Coverage</TableCell>
                    <TableCell align="right">Demand</TableCell>
                    <TableCell>Suggested learning</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {data.skill_gaps.map((gap, index) => (
                    <TableRow key={index}>
                      <TableCell>{String(gap.skill)}</TableCell>
                      <TableCell>{String(gap.category ?? "—")}</TableCell>
                      <TableCell align="right">{Number(gap.candidates_with_skill ?? 0)}</TableCell>
                      <TableCell align="right">{Number(gap.coverage_percent ?? 0).toFixed(1)}%</TableCell>
                      <TableCell align="right">{Number(gap.demand_score ?? 0).toFixed(0)}</TableCell>
                      <TableCell>
                        <Stack direction="row" gap={0.5} flexWrap="wrap">
                          {((gap.suggested_learning as string[]) ?? []).map((item) => (
                            <Chip key={item} size="small" variant="outlined" label={item} />
                          ))}
                        </Stack>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </SectionCard>
          </Grid>
        ) : null}
      </Grid>
    </>
  );
}
