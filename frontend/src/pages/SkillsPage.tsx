import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
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
  Drawer,
  Grid,
  IconButton,
  InputAdornment,
  List,
  ListItemAvatar,
  ListItemButton,
  ListItemText,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import DownloadIcon from "@mui/icons-material/Download";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import SearchIcon from "@mui/icons-material/Search";
import SyncIcon from "@mui/icons-material/Sync";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import { useSnackbar } from "notistack";

import { candidatesApi, skillsApi } from "@/api/endpoints";
import { EmptyState, Loading, PageHeader, StatCard, StatusChip } from "@/components/common";
import { useAuth } from "@/auth/AuthContext";
import type { SkillTaxonomyItem } from "@/types";

const MAX_SKILLS_CSV_BYTES = 2 * 1024 * 1024;

function skillsCsvFormatError(text: string): string | null {
  const stripped = text.replace(/^\uFEFF/, "").trimStart();
  if (!stripped) {
    return "The selected file is empty.";
  }
  const head = stripped.slice(0, 32).toLowerCase();
  if (head.startsWith("<!doctype") || head.startsWith("<html") || stripped.startsWith("{") || stripped.startsWith("[")) {
    return "Wrong file format. Upload a skills CSV, not JSON or HTML.";
  }
  const header = stripped.split(/\r?\n/, 1)[0] ?? "";
  const normalized = header.toLowerCase().replace(/[ -]+/g, "_");
  if (!normalized.includes("skill_name")) {
    return "Wrong CSV format. The header must include skill_name. Download the CSV from this page and keep those column names.";
  }
  return null;
}

function validateSkillsCsvFile(file: File): Promise<string | null> {
  if (!file.name.toLowerCase().endsWith(".csv")) {
    return Promise.resolve("Please choose a .csv file. Excel workbooks (.xlsx) are not accepted.");
  }
  if (file.size === 0) {
    return Promise.resolve("The selected file is empty.");
  }
  if (file.size > MAX_SKILLS_CSV_BYTES) {
    return Promise.resolve("CSV is too large (max 2 MB).");
  }
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(skillsCsvFormatError(String(reader.result ?? "")));
    reader.onerror = () => resolve("Could not read that file. Please upload a UTF-8 CSV.");
    reader.readAsText(file.slice(0, 64 * 1024));
  });
}

export default function SkillsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { enqueueSnackbar } = useSnackbar();
  const { isAdmin } = useAuth();
  const fileInput = useRef<HTMLInputElement | null>(null);

  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [selectedSkill, setSelectedSkill] = useState<SkillTaxonomyItem | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);

  const skillCandidates = useQuery({
    queryKey: ["candidates", "by-skill", selectedSkill?.name],
    queryFn: () =>
      candidatesApi.list({
        skills: [selectedSkill!.name],
        page_size: 100,
        sort_by: "experience",
        sort_dir: "desc",
      }),
    enabled: Boolean(selectedSkill),
  });

  const skills = useQuery({
    queryKey: ["skills", "list", search, category],
    queryFn: () => skillsApi.list({ search: search || undefined, category: category || undefined, limit: 500 }),
  });

  const categories = useQuery({ queryKey: ["skills", "categories"], queryFn: skillsApi.categories });
  const stats = useQuery({ queryKey: ["skills", "stats"], queryFn: skillsApi.stats });

  const reimport = useMutation({
    mutationFn: () => skillsApi.reimport(true),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
      enqueueSnackbar(
        `Imported ${Number(result.skills_created ?? result.created ?? 0)} new, updated ${Number(result.skills_updated ?? result.updated ?? 0)} skills`,
        { variant: "success" },
      );
    },
    onError: (error: Error) => enqueueSnackbar(error.message, { variant: "error" }),
  });

  const uploadCsv = useMutation({
    mutationFn: (file: File) => skillsApi.uploadCsv(file),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
      setPendingFile(null);
      enqueueSnackbar(
        `CSV imported: ${Number(result.skills_created ?? result.created ?? 0)} created, ${Number(result.skills_updated ?? result.updated ?? 0)} updated`,
        { variant: "success" },
      );
    },
    onError: (error: Error) => enqueueSnackbar(error.message, { variant: "error" }),
  });

  const downloadCsv = useMutation({
    mutationFn: () => skillsApi.downloadCsv(),
    onSuccess: () => enqueueSnackbar("Downloaded skills-knowledge-base.csv", { variant: "success" }),
    onError: (error: Error) => enqueueSnackbar(error.message, { variant: "error" }),
  });

  const grouped = useMemo(() => {
    const groups = new Map<string, SkillTaxonomyItem[]>();
    (skills.data ?? []).forEach((skill) => {
      const key = skill.category ?? "Uncategorised";
      groups.set(key, [...(groups.get(key) ?? []), skill]);
    });
    return [...groups.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [skills.data]);

  return (
    <>
      <PageHeader
        title="Skills knowledge base"
        subtitle="The authoritative taxonomy every resume is normalized against — categories, synonyms, parent/child hierarchy and related technologies."
        actions={
          isAdmin ? (
            <>
              <input
                ref={fileInput}
                type="file"
                accept=".csv,text/csv"
                hidden
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  if (!file) return;
                  void validateSkillsCsvFile(file).then((error) => {
                    if (error) {
                      enqueueSnackbar(error, { variant: "error" });
                      return;
                    }
                    uploadCsv.reset();
                    setPendingFile(file);
                  });
                }}
              />
              <Button
                variant="outlined"
                startIcon={<DownloadIcon />}
                disabled={downloadCsv.isPending}
                onClick={() => downloadCsv.mutate()}
              >
                {downloadCsv.isPending ? "Downloading…" : "Download CSV"}
              </Button>
              <Button
                variant="outlined"
                startIcon={<UploadFileIcon />}
                disabled={uploadCsv.isPending}
                onClick={() => fileInput.current?.click()}
              >
                Upload CSV
              </Button>
              <Button
                variant="contained"
                startIcon={<SyncIcon />}
                disabled={reimport.isPending}
                onClick={() => reimport.mutate()}
              >
                {reimport.isPending ? "Re-importing…" : "Re-import default CSV"}
              </Button>
            </>
          ) : undefined
        }
      />

      {isAdmin ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          Download the current CSV (filled with live skills and the importer columns), edit rows in Excel, then
          upload. Matching skill names are updated. Removed rows are not deleted. Use semicolons for lists such as
          synonyms and related skills.
        </Typography>
      ) : null}

      <Grid container spacing={2}>
        <Grid item xs={6} md={3}>
          <StatCard label="Skills" value={Number(stats.data?.total_skills ?? skills.data?.length ?? 0)} />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard label="Categories" value={categories.data?.length ?? 0} />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard label="Synonyms" value={Number(stats.data?.total_synonyms ?? 0)} />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatCard label="Relations" value={Number(stats.data?.total_relations ?? 0)} />
        </Grid>
      </Grid>

      <Card>
        <CardContent>
          <Stack direction={{ xs: "column", md: "row" }} gap={2}>
            <TextField
              fullWidth
              size="small"
              placeholder="Search skills, synonyms or technologies"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon color="action" />
                  </InputAdornment>
                ),
              }}
            />
            <TextField
              select
              size="small"
              label="Category"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              sx={{ minWidth: 240 }}
            >
              <MenuItem value="">All categories</MenuItem>
              {(categories.data ?? []).map((item) => (
                <MenuItem key={item.id} value={item.name}>
                  {item.name} ({item.skill_count})
                </MenuItem>
              ))}
            </TextField>
          </Stack>
        </CardContent>
      </Card>

      {skills.isLoading ? <Loading label="Loading taxonomy…" /> : null}

      {!skills.isLoading && grouped.length === 0 ? (
        <EmptyState title="No skills matched" description="Try a different search term or clear the filters." />
      ) : null}

      {grouped.map(([groupName, items]) => (
        <Accordion key={groupName} defaultExpanded={grouped.length <= 4} disableGutters>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography variant="h5">
              {groupName}
              <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                {items.length} skill(s)
              </Typography>
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Grid container spacing={2}>
              {items.map((skill) => (
                <Grid item xs={12} sm={6} md={4} key={skill.id}>
                  <Card variant="outlined" sx={{ height: "100%" }}>
                    <CardContent>
                      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" gap={1}>
                        <Box>
                          <Typography variant="subtitle2">{skill.name}</Typography>
                          <Typography variant="caption" color="text.secondary">
                            {skill.external_id}
                            {skill.technology_stack ? ` · ${skill.technology_stack}` : ""}
                            {skill.parent_skill ? ` · child of ${skill.parent_skill}` : ""}
                          </Typography>
                        </Box>
                        <Chip
                          size="small"
                          color={skill.candidate_count ? "primary" : "default"}
                          variant={skill.candidate_count ? "filled" : "outlined"}
                          clickable={skill.candidate_count > 0}
                          onClick={() => {
                            if (skill.candidate_count > 0) setSelectedSkill(skill);
                          }}
                          label={`${skill.candidate_count} candidate${skill.candidate_count === 1 ? "" : "s"}`}
                        />
                      </Stack>

                      {skill.description ? (
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                          {skill.description}
                        </Typography>
                      ) : null}

                      {skill.synonyms.length ? (
                        <Box sx={{ mt: 1 }}>
                          <Typography variant="caption" color="text.disabled">
                            Synonyms
                          </Typography>
                          <Stack direction="row" gap={0.5} flexWrap="wrap">
                            {skill.synonyms.slice(0, 6).map((synonym) => (
                              <Chip key={synonym} size="small" variant="outlined" label={synonym} />
                            ))}
                          </Stack>
                        </Box>
                      ) : null}

                      {skill.related_skills.length ? (
                        <Box sx={{ mt: 1 }}>
                          <Typography variant="caption" color="text.disabled">
                            Related
                          </Typography>
                          <Stack direction="row" gap={0.5} flexWrap="wrap">
                            {skill.related_skills.slice(0, 6).map((related) => (
                              <Chip key={related} size="small" color="primary" variant="outlined" label={related} />
                            ))}
                          </Stack>
                        </Box>
                      ) : null}

                      {skill.job_roles.length ? (
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                          Roles: {skill.job_roles.join(", ")}
                        </Typography>
                      ) : null}
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </AccordionDetails>
        </Accordion>
      ))}

      <Dialog
        open={Boolean(pendingFile)}
        onClose={() => {
          if (!uploadCsv.isPending) setPendingFile(null);
        }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Import skills CSV</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2" sx={{ mb: 1.5 }}>
            {pendingFile
              ? `${pendingFile.name} (${pendingFile.size < 1024 ? `${pendingFile.size} B` : `${(pendingFile.size / 1024).toFixed(1)} KB`})`
              : ""}
          </Typography>
          {uploadCsv.isError ? (
            <Alert severity="error" sx={{ mb: 1.5 }}>
              {uploadCsv.error.message}
            </Alert>
          ) : null}
          <Typography variant="body2" color="text.secondary">
            Required column: <strong>skill_name</strong>. Optional columns: skill_id, category, parent_skill,
            related_skills, technology_stack, job_role, experience_level, skill_synonyms, skill_description.
            Separate list values with a semicolon. Files that are not this CSV format are rejected and nothing is
            imported.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPendingFile(null)} disabled={uploadCsv.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={!pendingFile || uploadCsv.isPending}
            onClick={() => pendingFile && uploadCsv.mutate(pendingFile)}
          >
            {uploadCsv.isPending ? "Importing…" : "Import"}
          </Button>
        </DialogActions>
      </Dialog>

      <Drawer
        anchor="right"
        open={Boolean(selectedSkill)}
        onClose={() => setSelectedSkill(null)}
        PaperProps={{ sx: { width: { xs: "100%", sm: 440 } } }}
      >
        <Stack direction="row" alignItems="flex-start" justifyContent="space-between" sx={{ p: 2.5, pb: 1.5 }}>
          <Box>
            <Typography variant="h4">{selectedSkill?.name}</Typography>
            <Typography variant="body2" color="text.secondary">
              {selectedSkill?.category ? `${selectedSkill.category} · ` : ""}
              {selectedSkill?.candidate_count === 1
                ? "1 candidate with this skill"
                : `${selectedSkill?.candidate_count} candidates with this skill`}
            </Typography>
          </Box>
          <IconButton onClick={() => setSelectedSkill(null)} aria-label="Close candidate list">
            <CloseIcon />
          </IconButton>
        </Stack>
        <Divider />

        {skillCandidates.isLoading ? <Loading label="Loading candidates…" /> : null}

        {!skillCandidates.isLoading && (skillCandidates.data?.items.length ?? 0) === 0 ? (
          <Box sx={{ px: 2.5, py: 3 }}>
            <EmptyState title="No candidates yet" description="Nobody in the talent pool is mapped to this skill." />
          </Box>
        ) : null}

        <List sx={{ px: 1, py: 0.5 }}>
          {(skillCandidates.data?.items ?? []).map((candidate) => (
            <ListItemButton
              key={candidate.id}
              alignItems="flex-start"
              onClick={() => navigate(`/candidates/${candidate.id}`)}
              sx={{ borderRadius: 2, mb: 0.5 }}
            >
              <ListItemAvatar>
                <Avatar>{candidate.full_name.slice(0, 1)}</Avatar>
              </ListItemAvatar>
              <ListItemText
                primary={
                  <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1}>
                    <Typography variant="subtitle2">{candidate.full_name}</Typography>
                    <StatusChip status={candidate.status} />
                  </Stack>
                }
                secondary={
                  <>
                    <Typography variant="body2" color="text.secondary">
                      {candidate.current_title ?? "—"}
                      {candidate.current_company_name ? ` · ${candidate.current_company_name}` : ""}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block">
                      {Number(candidate.total_experience_years ?? 0).toFixed(1)} yrs
                      {candidate.email ? ` · ${candidate.email}` : ""}
                    </Typography>
                    {candidate.top_skills.length ? (
                      <Stack direction="row" gap={0.5} flexWrap="wrap" sx={{ mt: 0.75 }}>
                        {candidate.top_skills.slice(0, 4).map((name) => (
                          <Chip key={name} size="small" variant="outlined" label={name} />
                        ))}
                      </Stack>
                    ) : null}
                  </>
                }
              />
            </ListItemButton>
          ))}
        </List>

        {selectedSkill && (skillCandidates.data?.items.length ?? 0) > 0 ? (
          <Box sx={{ p: 2.5, pt: 1 }}>
            <Button
              fullWidth
              variant="outlined"
              onClick={() => navigate(`/candidates?skills=${encodeURIComponent(selectedSkill.name)}`)}
            >
              Open in candidates page
            </Button>
          </Box>
        ) : null}
      </Drawer>
    </>
  );
}
