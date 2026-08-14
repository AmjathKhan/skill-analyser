import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Avatar,
  Box,
  Button,
  Chip,
  Divider,
  Grid,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  Stack,
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
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import DescriptionIcon from "@mui/icons-material/Description";
import GroupsIcon from "@mui/icons-material/Groups";
import HowToRegIcon from "@mui/icons-material/HowToReg";
import PendingActionsIcon from "@mui/icons-material/PendingActions";
import dayjs from "dayjs";

import { dashboardApi } from "@/api/endpoints";
import { CardsSkeleton, ErrorState, PageHeader, SectionCard, StatCard } from "@/components/common";

const PIE_COLORS = ["#1a73e8", "#12b76a", "#f79009", "#e11d48", "#7c4dff", "#06b6d4", "#64748b", "#0891b2"];

export default function DashboardPage() {
  const navigate = useNavigate();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard"],
    queryFn: dashboardApi.get,
  });

  if (isLoading) {
    return (
      <>
        <PageHeader title="Dashboard" subtitle="Loading recruitment metrics…" />
        <CardsSkeleton count={5} />
      </>
    );
  }
  if (error || !data) return <ErrorState error={error} onRetry={refetch} />;

  const { cards } = data;

  return (
    <>
      <PageHeader
        title="Recruitment overview"
        subtitle={`Updated ${dayjs(data.generated_at).format("DD MMM YYYY, HH:mm")}`}
        actions={
          <>
            <Button variant="outlined" onClick={() => navigate("/search")}>
              Search talent
            </Button>
            <Button variant="contained" startIcon={<CloudUploadIcon />} onClick={() => navigate("/upload")}>
              Upload resumes
            </Button>
          </>
        }
      />

      <Grid container spacing={2}>
        <Grid item xs={12} sm={6} lg={2.4}>
          <StatCard
            label="Total candidates"
            value={cards.total_candidates}
            hint={`${cards.new_uploads_today} added today`}
            icon={<GroupsIcon />}
          />
        </Grid>
        <Grid item xs={12} sm={6} lg={2.4}>
          <StatCard
            label="Resumes processed"
            value={cards.uploaded_resumes}
            hint={cards.failed_resumes ? `${cards.failed_resumes} failed` : "All parsed successfully"}
            icon={<DescriptionIcon />}
          />
        </Grid>
        <Grid item xs={12} sm={6} lg={2.4}>
          <StatCard
            label="Shortlisted"
            value={cards.shortlisted}
            hint={`${cards.rejected} rejected`}
            icon={<HowToRegIcon />}
            color="success.main"
          />
        </Grid>
        <Grid item xs={12} sm={6} lg={2.4}>
          <StatCard
            label="Pending review"
            value={cards.pending_review}
            hint={cards.processing ? `${cards.processing} still processing` : "Queue clear"}
            icon={<PendingActionsIcon />}
            color="warning.main"
          />
        </Grid>
        <Grid item xs={12} sm={6} lg={2.4}>
          <StatCard
            label="Avg. experience"
            value={`${cards.average_experience_years.toFixed(1)} yrs`}
            hint={
              cards.average_match_score != null
                ? `Avg. match ${Math.round(cards.average_match_score)}%`
                : "Run a skill match to see scores"
            }
            icon={<AutoAwesomeIcon />}
            color="secondary.main"
          />
        </Grid>
      </Grid>

      <Grid container spacing={2}>
        <Grid item xs={12} lg={8}>
          <SectionCard title="Top skills in the talent pool" subtitle="Candidates per normalized skill">
            <Box sx={{ height: 320 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.top_skills.slice(0, 12)} layout="vertical" margin={{ left: 24 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} opacity={0.35} />
                  <XAxis type="number" allowDecimals={false} fontSize={12} />
                  <YAxis type="category" dataKey="name" width={130} fontSize={12} />
                  <ChartTooltip />
                  <Bar dataKey="value" fill="#1a73e8" radius={[0, 6, 6, 0]} name="Candidates" />
                </BarChart>
              </ResponsiveContainer>
            </Box>
          </SectionCard>
        </Grid>

        <Grid item xs={12} lg={4}>
          <SectionCard title="Technology distribution" subtitle="Share of the technology stacks">
            <Box sx={{ height: 320 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data.technology_distribution.slice(0, 8)}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={58}
                    outerRadius={95}
                    paddingAngle={2}
                  >
                    {data.technology_distribution.slice(0, 8).map((entry, index) => (
                      <Cell key={entry.name} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <ChartTooltip />
                  <Legend verticalAlign="bottom" height={54} iconSize={9} />
                </PieChart>
              </ResponsiveContainer>
            </Box>
          </SectionCard>
        </Grid>

        <Grid item xs={12} lg={8}>
          <SectionCard title="Hiring trends" subtitle="Uploads and pipeline movement by month">
            <Box sx={{ height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data.hiring_trends}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.35} />
                  <XAxis dataKey="period" fontSize={12} />
                  <YAxis allowDecimals={false} fontSize={12} />
                  <ChartTooltip />
                  <Legend />
                  <Line type="monotone" dataKey="uploads" stroke="#1a73e8" strokeWidth={2} name="Uploads" />
                  <Line
                    type="monotone"
                    dataKey="shortlisted"
                    stroke="#12b76a"
                    strokeWidth={2}
                    name="Shortlisted"
                  />
                  <Line type="monotone" dataKey="rejected" stroke="#f04438" strokeWidth={2} name="Rejected" />
                </LineChart>
              </ResponsiveContainer>
            </Box>
          </SectionCard>
        </Grid>

        <Grid item xs={12} lg={4}>
          <SectionCard title="Experience distribution" subtitle="Candidates per experience band">
            <Box sx={{ height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.experience_distribution}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.35} />
                  <XAxis dataKey="name" fontSize={12} />
                  <YAxis allowDecimals={false} fontSize={12} />
                  <ChartTooltip />
                  <Bar dataKey="value" fill="#7c4dff" radius={[6, 6, 0, 0]} name="Candidates" />
                </BarChart>
              </ResponsiveContainer>
            </Box>
          </SectionCard>
        </Grid>

        <Grid item xs={12} lg={5}>
          <SectionCard title="AI recommendations" subtitle="Suggested next actions from the knowledge graph">
            {data.ai_recommendations.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                Upload more resumes to unlock recommendations.
              </Typography>
            ) : (
              <Stack divider={<Divider flexItem />} gap={1.5}>
                {data.ai_recommendations.slice(0, 5).map((item, index) => (
                  <Stack key={index} gap={0.5}>
                    <Typography variant="subtitle2">{String(item.title ?? "Recommendation")}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {String(item.detail ?? "")}
                    </Typography>
                  </Stack>
                ))}
              </Stack>
            )}
          </SectionCard>
        </Grid>

        <Grid item xs={12} lg={7}>
          <SectionCard
            title="Recent activity"
            subtitle="Audit trail across uploads, matches and status changes"
            action={
              <Button size="small" onClick={() => navigate("/users")}>
                View all
              </Button>
            }
          >
            <List dense disablePadding>
              {data.recent_activity.slice(0, 8).map((item) => (
                <ListItem key={item.id} disableGutters>
                  <ListItemAvatar>
                    <Avatar sx={{ width: 32, height: 32, bgcolor: "action.hover", color: "text.primary" }}>
                      {item.actor.charAt(0).toUpperCase()}
                    </Avatar>
                  </ListItemAvatar>
                  <ListItemText
                    primary={item.description ?? item.action}
                    secondary={`${item.actor} · ${dayjs(item.created_at).format("DD MMM HH:mm")}`}
                    primaryTypographyProps={{ variant: "body2" }}
                  />
                  <Chip size="small" variant="outlined" label={item.action.replace(/_/g, " ")} />
                </ListItem>
              ))}
            </List>
          </SectionCard>
        </Grid>
      </Grid>
    </>
  );
}
