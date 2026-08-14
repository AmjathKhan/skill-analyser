import { useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { useSnackbar } from "notistack";
import dayjs from "dayjs";

import { authApi, systemApi } from "@/api/endpoints";
import { useAuth } from "@/auth/AuthContext";
import { useColorMode } from "@/ColorMode";
import { PageHeader, SectionCard } from "@/components/common";

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const { mode, toggle } = useColorMode();
  const { enqueueSnackbar } = useSnackbar();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const health = useQuery({ queryKey: ["health"], queryFn: systemApi.health });
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: authApi.sessions });

  const changePassword = useMutation({
    mutationFn: () => authApi.changePassword(currentPassword, newPassword),
    onSuccess: () => {
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      enqueueSnackbar("Password changed — please sign in again", { variant: "success" });
      void logout();
    },
    onError: (error: Error) => enqueueSnackbar(error.message, { variant: "error" }),
  });

  const submitPassword = (event: FormEvent) => {
    event.preventDefault();
    if (newPassword !== confirmPassword) {
      enqueueSnackbar("Passwords do not match", { variant: "warning" });
      return;
    }
    changePassword.mutate();
  };

  return (
    <>
      <PageHeader title="Settings" subtitle="Your profile, security and the platform's AI configuration." />

      <Grid container spacing={2}>
        <Grid item xs={12} md={5}>
          <SectionCard title="Profile" subtitle="Signed in account">
            <Stack direction="row" gap={2} alignItems="center">
              <Avatar sx={{ width: 64, height: 64, bgcolor: "primary.main", fontSize: 26 }}>
                {user?.full_name.charAt(0)}
              </Avatar>
              <Box>
                <Typography variant="h4">{user?.full_name}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {user?.email}
                </Typography>
                <Chip size="small" color="primary" label={user?.role_label} sx={{ mt: 0.5 }} />
              </Box>
            </Stack>

            <Table size="small" sx={{ mt: 2 }}>
              <TableBody>
                <TableRow>
                  <TableCell>Department</TableCell>
                  <TableCell align="right">{user?.department ?? "—"}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Phone</TableCell>
                  <TableCell align="right">{user?.phone ?? "—"}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Member since</TableCell>
                  <TableCell align="right">
                    {user ? dayjs(user.created_at).format("DD MMM YYYY") : "—"}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Last login</TableCell>
                  <TableCell align="right">
                    {user?.last_login_at ? dayjs(user.last_login_at).format("DD MMM YYYY HH:mm") : "—"}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>

            <Divider sx={{ my: 2 }} />
            <Typography variant="subtitle2" gutterBottom>
              Permissions
            </Typography>
            <Stack direction="row" gap={0.5} flexWrap="wrap">
              {(user?.permissions ?? []).map((permission) => (
                <Chip key={permission} size="small" variant="outlined" label={permission} />
              ))}
            </Stack>

            <Divider sx={{ my: 2 }} />
            <Stack direction="row" alignItems="center" justifyContent="space-between">
              <Typography variant="body2">Dark mode</Typography>
              <Switch checked={mode === "dark"} onChange={toggle} />
            </Stack>
          </SectionCard>
        </Grid>

        <Grid item xs={12} md={7}>
          <SectionCard title="Change password" subtitle="Minimum 8 characters with letters and numbers">
            <Box component="form" onSubmit={submitPassword}>
              <Stack gap={2}>
                <TextField
                  label="Current password"
                  type="password"
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                  required
                />
                <TextField
                  label="New password"
                  type="password"
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  required
                />
                <TextField
                  label="Confirm new password"
                  type="password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  required
                  error={confirmPassword.length > 0 && confirmPassword !== newPassword}
                />
                <Box>
                  <Button type="submit" variant="contained" disabled={changePassword.isPending}>
                    Update password
                  </Button>
                </Box>
              </Stack>
            </Box>
          </SectionCard>

          <Card sx={{ mt: 2 }}>
            <CardContent>
              <Typography variant="h4" gutterBottom>
                Active sessions
              </Typography>
              <Table size="small">
                <TableBody>
                  {(sessions.data ?? []).map((session, index) => (
                    <TableRow key={index}>
                      <TableCell>{String(session.ip_address ?? "unknown IP")}</TableCell>
                      <TableCell>{String(session.user_agent ?? "").slice(0, 60) || "—"}</TableCell>
                      <TableCell align="right">
                        {session.created_at
                          ? dayjs(String(session.created_at)).format("DD MMM HH:mm")
                          : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Button sx={{ mt: 1.5 }} color="error" onClick={() => logout(true)}>
                Sign out of all devices
              </Button>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12}>
          <SectionCard title="Platform status" subtitle="AI stack currently powering the analyser">
            <Grid container spacing={2}>
              {[
                { label: "Status", value: health.data?.status ?? "—" },
                { label: "Version", value: health.data?.version ?? "—" },
                { label: "Environment", value: health.data?.environment ?? "—" },
                { label: "Database", value: health.data?.database ? "connected" : "unavailable" },
                {
                  label: "Graph backend",
                  value: `${health.data?.graph_backend ?? "—"}${health.data?.graph_healthy ? "" : " (degraded)"}`,
                },
                { label: "Vector backend", value: health.data?.vector_backend ?? "—" },
                { label: "Embedding model", value: health.data?.embedding_model ?? "—" },
                { label: "LLM backend", value: health.data?.llm_backend ?? "—" },
                { label: "Skills loaded", value: health.data?.skills_loaded ?? "—" },
                { label: "Celery", value: health.data?.celery_enabled ? "enabled" : "inline tasks" },
              ].map((item) => (
                <Grid item xs={6} md={3} key={item.label}>
                  <Typography variant="caption" color="text.secondary">
                    {item.label}
                  </Typography>
                  <Typography variant="body2" fontWeight={600}>
                    {item.value}
                  </Typography>
                </Grid>
              ))}
            </Grid>
          </SectionCard>
        </Grid>
      </Grid>
    </>
  );
}
