import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDropzone, type FileRejection } from "react-dropzone";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  FormControlLabel,
  IconButton,
  LinearProgress,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import InsertDriveFileIcon from "@mui/icons-material/InsertDriveFile";
import { useSnackbar } from "notistack";

import { resumesApi } from "@/api/endpoints";
import { PageHeader, SectionCard } from "@/components/common";
import type { UploadResponse } from "@/types";

const ACCEPTED = {
  "application/pdf": [".pdf"],
  "application/msword": [".doc"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
  "text/plain": [".txt"],
};

const ALLOWED_EXTENSIONS = [".pdf", ".doc", ".docx", ".txt"];
const MAX_FILES = 25;
const MAX_FILE_BYTES = 15 * 1024 * 1024;

function hasAllowedExtension(name: string): boolean {
  const lower = name.toLowerCase();
  return ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function UploadPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { enqueueSnackbar } = useSnackbar();

  const [files, setFiles] = useState<File[]>([]);
  const [waitForParsing, setWaitForParsing] = useState(true);
  const [allowDuplicates, setAllowDuplicates] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);

  const onDrop = useCallback(
    (accepted: File[], rejected: FileRejection[]) => {
      const recovered = rejected
        .filter(
          (item) =>
            hasAllowedExtension(item.file.name) &&
            item.errors.every((error) => error.code === "file-invalid-type"),
        )
        .map((item) => item.file);
      const blocked = rejected.filter((item) => !recovered.includes(item.file));
      if (blocked.length) {
        enqueueSnackbar(
          blocked
            .map((item) => `${item.file.name}: ${item.errors.map((error) => error.message).join(", ")}`)
            .join(" · "),
          { variant: "warning" },
        );
      }
      setFiles((current) => [...current, ...accepted, ...recovered].slice(0, MAX_FILES));
    },
    [enqueueSnackbar],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED,
    maxFiles: MAX_FILES,
    maxSize: MAX_FILE_BYTES,
  });

  const upload = useMutation({
    mutationFn: () => resumesApi.upload(files, { wait: waitForParsing, allowDuplicates }),
    onSuccess: (response) => {
      setResult(response);
      setFiles([]);
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["candidates"] });
      enqueueSnackbar(
        `${response.uploaded} uploaded · ${response.duplicates} duplicate · ${response.failed} failed`,
        { variant: response.failed ? "warning" : "success" },
      );
    },
    onError: (error: Error) => enqueueSnackbar(error.message, { variant: "error" }),
  });

  return (
    <>
      <PageHeader
        title="Upload resumes"
        subtitle="PDF, DOC, DOCX or TXT. Files are parsed, normalized against the Skills Knowledge Base and synced into the knowledge graph."
      />

      <Card>
        <CardContent>
          <Box
            {...getRootProps()}
            sx={{
              border: "2px dashed",
              borderColor: isDragActive ? "primary.main" : "divider",
              borderRadius: 3,
              p: { xs: 4, md: 6 },
              textAlign: "center",
              cursor: "pointer",
              bgcolor: isDragActive ? "action.hover" : "transparent",
              transition: "all .15s ease",
            }}
          >
            <input {...getInputProps()} />
            <CloudUploadIcon sx={{ fontSize: 46, color: "primary.main" }} />
            <Typography variant="h4" sx={{ mt: 1 }}>
              {isDragActive ? "Drop the resumes here" : "Drag & drop resumes, or click to browse"}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              PDF, DOC, DOCX or TXT · up to {MAX_FILES} files per batch · max 15 MB each
            </Typography>
          </Box>

          <Stack direction={{ xs: "column", sm: "row" }} gap={2} sx={{ mt: 2 }} alignItems="center">
            <FormControlLabel
              control={
                <Switch
                  checked={waitForParsing}
                  onChange={(event) => setWaitForParsing(event.target.checked)}
                />
              }
              label="Parse immediately and show results"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={allowDuplicates}
                  onChange={(event) => setAllowDuplicates(event.target.checked)}
                />
              }
              label="Allow duplicates"
            />
            <Box sx={{ flex: 1 }} />
            <Button
              variant="contained"
              size="large"
              disabled={files.length === 0 || upload.isPending}
              onClick={() => upload.mutate()}
            >
              {upload.isPending ? "Processing…" : `Upload ${files.length || ""}`}
            </Button>
          </Stack>

          {upload.isPending ? <LinearProgress sx={{ mt: 2, borderRadius: 2 }} /> : null}
        </CardContent>
      </Card>

      {files.length > 0 ? (
        <SectionCard title="Selected files" subtitle={`${files.length} file(s) ready to upload`}>
          <Table size="small">
            <TableBody>
              {files.map((file, index) => (
                <TableRow key={`${file.name}-${index}`}>
                  <TableCell width={44}>
                    <InsertDriveFileIcon color="action" />
                  </TableCell>
                  <TableCell>{file.name}</TableCell>
                  <TableCell width={110}>{formatBytes(file.size)}</TableCell>
                  <TableCell width={64} align="right">
                    <IconButton
                      size="small"
                      onClick={() => setFiles((current) => current.filter((_, i) => i !== index))}
                      aria-label={`Remove ${file.name}`}
                    >
                      <DeleteOutlineIcon fontSize="small" />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </SectionCard>
      ) : null}

      {result ? (
        <SectionCard
          title="Processing results"
          subtitle={
            result.queued
              ? "Files were queued for background parsing"
              : "Extraction, skill normalization, embeddings and graph sync completed"
          }
        >
          {result.failed > 0 ? (
            <Alert severity="warning" sx={{ mb: 2 }}>
              {result.failed} file(s) could not be processed. Scanned PDFs need OCR enabled on the server.
            </Alert>
          ) : null}
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>File</TableCell>
                <TableCell>Status</TableCell>
                <TableCell align="right">Skills</TableCell>
                <TableCell align="right">Graph edges</TableCell>
                <TableCell align="right">Duration</TableCell>
                <TableCell align="right">Candidate</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {result.results.map((item) => (
                <TableRow key={`${item.filename}-${item.resume_id ?? "x"}`} hover>
                  <TableCell>{item.filename}</TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={item.is_duplicate ? "duplicate" : item.status}
                      color={
                        item.error
                          ? "error"
                          : item.is_duplicate
                            ? "warning"
                            : item.status === "completed"
                              ? "success"
                              : "default"
                      }
                      variant="outlined"
                    />
                    {item.error ? (
                      <Typography variant="caption" color="error" display="block">
                        {item.error}
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell align="right">{item.processing?.skills_normalized ?? "—"}</TableCell>
                  <TableCell align="right">{item.processing?.graph_edges ?? "—"}</TableCell>
                  <TableCell align="right">
                    {item.processing ? `${item.processing.duration_ms} ms` : "—"}
                  </TableCell>
                  <TableCell align="right">
                    {item.candidate_id ? (
                      <Button size="small" onClick={() => navigate(`/candidates/${item.candidate_id}`)}>
                        View profile
                      </Button>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </SectionCard>
      ) : null}
    </>
  );
}
