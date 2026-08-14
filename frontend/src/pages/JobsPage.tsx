import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Autocomplete,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  IconButton,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditIcon from "@mui/icons-material/Edit";
import PsychologyIcon from "@mui/icons-material/Psychology";
import { useSnackbar } from "notistack";
import dayjs from "dayjs";

import { jobsApi, skillsApi } from "@/api/endpoints";
import { EmptyState, Loading, PageHeader } from "@/components/common";
import { useAuth } from "@/auth/AuthContext";
import type { JobRequirement } from "@/types";

interface FormState {
  id?: number;
  title: string;
  department: string;
  location: string;
  description: string;
  min_experience_years: number;
  max_experience_years: string;
  required_skills: string[];
  preferred_skills: string[];
  preferred_certifications: string[];
  education_requirement: string;
  is_active: boolean;
}

const EMPTY_FORM: FormState = {
  title: "",
  department: "",
  location: "",
  description: "",
  min_experience_years: 0,
  max_experience_years: "",
  required_skills: [],
  preferred_skills: [],
  preferred_certifications: [],
  education_requirement: "",
  is_active: true,
};

export default function JobsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { enqueueSnackbar } = useSnackbar();
  const { can } = useAuth();

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);

  const jobs = useQuery({ queryKey: ["jobs", "all"], queryFn: () => jobsApi.list(false) });

  const { data: skillOptions } = useQuery({
    queryKey: ["skills", "options"],
    queryFn: () => skillsApi.list({ limit: 400 }),
    staleTime: 10 * 60_000,
  });

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        title: form.title,
        department: form.department || null,
        location: form.location || null,
        description: form.description || null,
        min_experience_years: Number(form.min_experience_years) || 0,
        max_experience_years: form.max_experience_years ? Number(form.max_experience_years) : null,
        required_skills: form.required_skills,
        preferred_skills: form.preferred_skills,
        preferred_certifications: form.preferred_certifications,
        education_requirement: form.education_requirement || null,
        is_active: form.is_active,
      };
      return form.id ? jobsApi.update(form.id, payload) : jobsApi.create(payload);
    },
    onSuccess: () => {
      setOpen(false);
      setForm(EMPTY_FORM);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      enqueueSnackbar("Job requirement saved", { variant: "success" });
    },
    onError: (error: Error) => enqueueSnackbar(error.message, { variant: "error" }),
  });

  const remove = useMutation({
    mutationFn: (id: number) => jobsApi.remove(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      enqueueSnackbar("Job requirement archived", { variant: "success" });
    },
    onError: (error: Error) => enqueueSnackbar(error.message, { variant: "error" }),
  });

  const edit = (requirement: JobRequirement) => {
    setForm({
      id: requirement.id,
      title: requirement.title,
      department: requirement.department ?? "",
      location: requirement.location ?? "",
      description: requirement.description ?? "",
      min_experience_years: requirement.min_experience_years,
      max_experience_years: requirement.max_experience_years?.toString() ?? "",
      required_skills: requirement.required_skills,
      preferred_skills: requirement.preferred_skills,
      preferred_certifications: requirement.preferred_certifications,
      education_requirement: requirement.education_requirement ?? "",
      is_active: requirement.is_active,
    });
    setOpen(true);
  };

  const options = (skillOptions ?? []).map((skill) => skill.name);

  return (
    <>
      <PageHeader
        title="Job requirements"
        subtitle="Reusable role definitions that drive the AI skill match and gap analysis."
        actions={
          can("candidate:write") ? (
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => {
                setForm(EMPTY_FORM);
                setOpen(true);
              }}
            >
              New requirement
            </Button>
          ) : undefined
        }
      />

      {jobs.isLoading ? <Loading label="Loading job requirements…" /> : null}

      {!jobs.isLoading && (jobs.data ?? []).length === 0 ? (
        <EmptyState
          title="No job requirements yet"
          description="Create a role with its required and preferred skills to rank candidates against it in one click."
        />
      ) : null}

      <Grid container spacing={2}>
        {(jobs.data ?? []).map((requirement) => (
          <Grid item xs={12} md={6} key={requirement.id}>
            <Card sx={{ height: "100%", opacity: requirement.is_active ? 1 : 0.6 }}>
              <CardContent>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start" gap={1}>
                  <div>
                    <Typography variant="h4">{requirement.title}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {[requirement.department, requirement.location].filter(Boolean).join(" · ") || "—"} ·{" "}
                      {requirement.min_experience_years}
                      {requirement.max_experience_years ? `–${requirement.max_experience_years}` : "+"} yrs ·
                      created {dayjs(requirement.created_at).format("DD MMM YYYY")}
                    </Typography>
                  </div>
                  <Stack direction="row">
                    <Tooltip title="Run skill match">
                      <IconButton onClick={() => navigate("/skill-match")} size="small">
                        <PsychologyIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    {can("candidate:write") ? (
                      <>
                        <Tooltip title="Edit">
                          <IconButton size="small" onClick={() => edit(requirement)}>
                            <EditIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Archive">
                          <IconButton size="small" onClick={() => remove.mutate(requirement.id)}>
                            <DeleteOutlineIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </>
                    ) : null}
                  </Stack>
                </Stack>

                {requirement.description ? (
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    {requirement.description}
                  </Typography>
                ) : null}

                <Stack direction="row" gap={0.5} flexWrap="wrap" sx={{ mt: 1.5 }}>
                  {requirement.required_skills.map((skill) => (
                    <Chip key={skill} size="small" color="primary" label={skill} />
                  ))}
                  {requirement.preferred_skills.map((skill) => (
                    <Chip key={skill} size="small" variant="outlined" label={skill} />
                  ))}
                </Stack>

                {requirement.preferred_certifications.length ? (
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                    Certifications: {requirement.preferred_certifications.join(", ")}
                  </Typography>
                ) : null}
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>{form.id ? "Edit job requirement" : "New job requirement"}</DialogTitle>
        <DialogContent dividers>
          <Grid container spacing={2} sx={{ pt: 1 }}>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Title"
                value={form.title}
                onChange={(event) => setForm({ ...form, title: event.target.value })}
              />
            </Grid>
            <Grid item xs={6} md={3}>
              <TextField
                fullWidth
                label="Department"
                value={form.department}
                onChange={(event) => setForm({ ...form, department: event.target.value })}
              />
            </Grid>
            <Grid item xs={6} md={3}>
              <TextField
                fullWidth
                label="Location"
                value={form.location}
                onChange={(event) => setForm({ ...form, location: event.target.value })}
              />
            </Grid>
            <Grid item xs={6} md={3}>
              <TextField
                fullWidth
                type="number"
                label="Min experience"
                value={form.min_experience_years}
                onChange={(event) =>
                  setForm({ ...form, min_experience_years: Number(event.target.value) })
                }
              />
            </Grid>
            <Grid item xs={6} md={3}>
              <TextField
                fullWidth
                type="number"
                label="Max experience"
                value={form.max_experience_years}
                onChange={(event) => setForm({ ...form, max_experience_years: event.target.value })}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Education requirement"
                value={form.education_requirement}
                onChange={(event) => setForm({ ...form, education_requirement: event.target.value })}
              />
            </Grid>
            <Grid item xs={12}>
              <Autocomplete
                multiple
                freeSolo
                options={options}
                value={form.required_skills}
                onChange={(_event, value) => setForm({ ...form, required_skills: value as string[] })}
                renderInput={(params) => <TextField {...params} label="Required skills" />}
              />
            </Grid>
            <Grid item xs={12}>
              <Autocomplete
                multiple
                freeSolo
                options={options}
                value={form.preferred_skills}
                onChange={(_event, value) => setForm({ ...form, preferred_skills: value as string[] })}
                renderInput={(params) => <TextField {...params} label="Preferred skills" />}
              />
            </Grid>
            <Grid item xs={12}>
              <Autocomplete
                multiple
                freeSolo
                options={[]}
                value={form.preferred_certifications}
                onChange={(_event, value) =>
                  setForm({ ...form, preferred_certifications: value as string[] })
                }
                renderInput={(params) => <TextField {...params} label="Preferred certifications" />}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                multiline
                minRows={3}
                label="Description"
                value={form.description}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
              />
            </Grid>
            <Grid item xs={12}>
              <Stack direction="row" alignItems="center" gap={1}>
                <Switch
                  checked={form.is_active}
                  onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
                />
                <Typography variant="body2">Active</Typography>
              </Stack>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={form.title.trim().length < 2 || form.required_skills.length === 0 || save.isPending}
            onClick={() => save.mutate()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
