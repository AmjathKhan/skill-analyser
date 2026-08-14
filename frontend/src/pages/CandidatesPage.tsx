import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { DataGrid, type GridColDef, type GridPaginationModel } from "@mui/x-data-grid";
import DownloadIcon from "@mui/icons-material/Download";
import FilterAltOffIcon from "@mui/icons-material/FilterAltOff";
import dayjs from "dayjs";

import { candidatesApi, reportsApi, skillsApi } from "@/api/endpoints";
import { PageHeader, ScoreBadge, StatusChip } from "@/components/common";
import type { CandidateListItem } from "@/types";

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

interface Filters {
  search: string;
  status: string[];
  skills: string[];
  minExperience: string;
  location: string;
  company: string;
}

const EMPTY_FILTERS: Filters = {
  search: "",
  status: [],
  skills: [],
  minExperience: "",
  location: "",
  company: "",
};

export default function CandidatesPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [filters, setFilters] = useState<Filters>(() => ({
    ...EMPTY_FILTERS,
    skills: searchParams.getAll("skills").filter(Boolean),
  }));
  const [pagination, setPagination] = useState<GridPaginationModel>({ page: 0, pageSize: 20 });
  const [sortBy, setSortBy] = useState("created_at");

  const { data: skillOptions } = useQuery({
    queryKey: ["skills", "options"],
    queryFn: () => skillsApi.list({ limit: 300 }),
    staleTime: 10 * 60_000,
  });

  const query = useQuery({
    queryKey: ["candidates", filters, pagination, sortBy],
    queryFn: () =>
      candidatesApi.list({
        search: filters.search || undefined,
        status: filters.status.length ? filters.status : undefined,
        skills: filters.skills.length ? filters.skills : undefined,
        min_experience: filters.minExperience ? Number(filters.minExperience) : undefined,
        location: filters.location || undefined,
        company: filters.company || undefined,
        sort_by: sortBy,
        sort_dir: sortBy === "name" ? "asc" : "desc",
        page: pagination.page + 1,
        page_size: pagination.pageSize,
      }),
    placeholderData: keepPreviousData,
  });

  const columns = useMemo<GridColDef<CandidateListItem>[]>(
    () => [
      {
        field: "full_name",
        headerName: "Candidate",
        flex: 1.4,
        minWidth: 220,
        renderCell: ({ row }) => (
          <Box sx={{ py: 0.75 }}>
            <Typography variant="body2" fontWeight={600}>
              {row.full_name}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {row.current_title ?? "—"}
              {row.current_company_name ? ` · ${row.current_company_name}` : ""}
            </Typography>
          </Box>
        ),
      },
      {
        field: "total_experience_years",
        headerName: "Experience",
        width: 120,
        valueFormatter: (value: number) => `${Number(value ?? 0).toFixed(1)} yrs`,
      },
      {
        field: "top_skills",
        headerName: "Top skills",
        flex: 1.6,
        minWidth: 260,
        sortable: false,
        renderCell: ({ row }) => (
          <Stack direction="row" gap={0.5} flexWrap="wrap" sx={{ py: 1 }}>
            {row.top_skills.slice(0, 4).map((skill) => (
              <Chip key={skill} size="small" label={skill} variant="outlined" />
            ))}
            {row.top_skills.length > 4 ? (
              <Chip size="small" label={`+${row.top_skills.length - 4}`} />
            ) : null}
          </Stack>
        ),
      },
      {
        field: "city",
        headerName: "Location",
        width: 140,
        valueGetter: (_value, row) => [row.city, row.country].filter(Boolean).join(", ") || "—",
      },
      {
        field: "status",
        headerName: "Status",
        width: 140,
        renderCell: ({ row }) => <StatusChip status={row.status} />,
      },
      {
        field: "last_match_score",
        headerName: "AI score",
        width: 110,
        renderCell: ({ row }) =>
          row.last_match_score != null ? <ScoreBadge score={row.last_match_score} size="small" /> : "—",
      },
      {
        field: "created_at",
        headerName: "Added",
        width: 120,
        valueFormatter: (value: string) => dayjs(value).format("DD MMM YY"),
      },
    ],
    [],
  );

  const rows = query.data?.items ?? [];

  return (
    <>
      <PageHeader
        title="Candidates"
        subtitle={`${query.data?.meta.total ?? 0} profiles extracted from uploaded resumes`}
        actions={
          <Button
            variant="outlined"
            startIcon={<DownloadIcon />}
            onClick={() => reportsApi.exportCandidates()}
          >
            Export CSV
          </Button>
        }
      />

      <Card>
        <CardContent>
          <Grid container spacing={2}>
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                label="Search name, email, title, company or skill"
                value={filters.search}
                onChange={(event) => setFilters({ ...filters, search: event.target.value })}
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <Autocomplete
                multiple
                size="small"
                options={(skillOptions ?? []).map((skill) => skill.name)}
                value={filters.skills}
                onChange={(_event, value) => setFilters({ ...filters, skills: value })}
                renderInput={(params) => <TextField {...params} label="Must have skills" />}
              />
            </Grid>
            <Grid item xs={6} md={2}>
              <TextField
                fullWidth
                select
                label="Status"
                SelectProps={{ multiple: true, value: filters.status }}
                onChange={(event) =>
                  setFilters({ ...filters, status: event.target.value as unknown as string[] })
                }
              >
                {STATUS_OPTIONS.map((status) => (
                  <MenuItem key={status} value={status}>
                    {status.replace(/_/g, " ")}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item xs={6} md={2}>
              <TextField
                fullWidth
                type="number"
                label="Min experience"
                value={filters.minExperience}
                onChange={(event) => setFilters({ ...filters, minExperience: event.target.value })}
              />
            </Grid>
            <Grid item xs={12} md={3}>
              <TextField
                fullWidth
                label="Location"
                value={filters.location}
                onChange={(event) => setFilters({ ...filters, location: event.target.value })}
              />
            </Grid>
            <Grid item xs={12} md={3}>
              <TextField
                fullWidth
                label="Company"
                value={filters.company}
                onChange={(event) => setFilters({ ...filters, company: event.target.value })}
              />
            </Grid>
            <Grid item xs={12} md={3}>
              <TextField
                fullWidth
                select
                label="Sort by"
                value={sortBy}
                onChange={(event) => setSortBy(event.target.value)}
              >
                <MenuItem value="created_at">Newest first</MenuItem>
                <MenuItem value="name">Name (A-Z)</MenuItem>
                <MenuItem value="experience">Experience</MenuItem>
                <MenuItem value="ai_score">AI match score</MenuItem>
                <MenuItem value="status">Status</MenuItem>
              </TextField>
            </Grid>
            <Grid item xs={12} md={3}>
              <Button
                fullWidth
                variant="text"
                startIcon={<FilterAltOffIcon />}
                onClick={() => setFilters(EMPTY_FILTERS)}
              >
                Clear filters
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Card>
        <DataGrid
          autoHeight
          rows={rows}
          columns={columns}
          getRowId={(row) => row.id}
          loading={query.isFetching}
          rowCount={query.data?.meta.total ?? 0}
          paginationMode="server"
          paginationModel={pagination}
          onPaginationModelChange={setPagination}
          pageSizeOptions={[10, 20, 50, 100]}
          disableColumnMenu
          rowHeight={64}
          onRowClick={(params) => navigate(`/candidates/${params.id}`)}
          sx={{
            border: 0,
            "& .MuiDataGrid-row": { cursor: "pointer" },
            "& .MuiDataGrid-cell:focus, & .MuiDataGrid-cell:focus-within": { outline: "none" },
          }}
        />
      </Card>
    </>
  );
}
