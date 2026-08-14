import { useState, type FormEvent } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Link,
  Stack,
  TextField,
  Typography,
} from "@mui/material";

import { authApi } from "@/api/endpoints";

export default function ForgotPasswordPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [stage, setStage] = useState<"request" | "reset">("request");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function requestReset(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await authApi.forgotPassword(email.trim());
      setMessage(response.message);
      if (response.reset_token) {
        setToken(response.reset_token);
      }
      setStage("reset");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  async function submitReset(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await authApi.resetPassword(token.trim(), password);
      navigate("/login", { replace: true });
    } catch (resetError) {
      setError(resetError instanceof Error ? resetError.message : "Reset failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        p: 2,
        background: "linear-gradient(140deg,#0b1020 0%,#132347 45%,#1a73e8 100%)",
      }}
    >
      <Card sx={{ width: "100%", maxWidth: 460 }}>
        <CardContent sx={{ p: { xs: 3, md: 4 } }}>
          <Typography variant="h2">Reset password</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 3 }}>
            {stage === "request"
              ? "We will email you a single-use reset link."
              : "Paste the reset token and choose a new password."}
          </Typography>

          {message ? (
            <Alert severity="info" sx={{ mb: 2 }}>
              {message}
            </Alert>
          ) : null}
          {error ? (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          ) : null}

          {stage === "request" ? (
            <Box component="form" onSubmit={requestReset}>
              <Stack gap={2}>
                <TextField
                  label="Work email"
                  type="email"
                  size="medium"
                  required
                  fullWidth
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
                <Button type="submit" variant="contained" size="large" disabled={busy}>
                  {busy ? "Sending…" : "Send reset link"}
                </Button>
              </Stack>
            </Box>
          ) : (
            <Box component="form" onSubmit={submitReset}>
              <Stack gap={2}>
                <TextField
                  label="Reset token"
                  size="medium"
                  required
                  fullWidth
                  multiline
                  minRows={2}
                  value={token}
                  onChange={(event) => setToken(event.target.value)}
                />
                <TextField
                  label="New password"
                  type="password"
                  size="medium"
                  required
                  fullWidth
                  helperText="At least 8 characters with upper, lower, digit and symbol."
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
                <Button type="submit" variant="contained" size="large" disabled={busy}>
                  {busy ? "Updating…" : "Set new password"}
                </Button>
              </Stack>
            </Box>
          )}

          <Typography variant="body2" sx={{ mt: 3 }}>
            <Link component={RouterLink} to="/login" underline="hover">
              Back to sign in
            </Link>
          </Typography>
        </CardContent>
      </Card>
    </Box>
  );
}
