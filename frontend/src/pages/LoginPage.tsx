import { useState, type FormEvent } from "react";
import { Link as RouterLink, Navigate, useLocation, useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Divider,
  FormControlLabel,
  IconButton,
  InputAdornment,
  Link,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import Visibility from "@mui/icons-material/Visibility";
import VisibilityOff from "@mui/icons-material/VisibilityOff";

import { useAuth } from "@/auth/AuthContext";

const HIGHLIGHTS = [
  "Parse PDF, DOC and DOCX resumes with AI entity extraction",
  "Normalize every skill against your Skills Knowledge Base",
  "Rank candidates with explainable Graph RAG scoring",
];

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: { pathname: string } } };

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) {
    return <Navigate to={location.state?.from?.pathname ?? "/dashboard"} replace />;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password, remember);
      navigate(location.state?.from?.pathname ?? "/dashboard", { replace: true });
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "Unable to sign in");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "grid",
        gridTemplateColumns: { xs: "1fr", md: "1.1fr 1fr" },
        background: "linear-gradient(140deg,#0b1020 0%,#132347 45%,#1a73e8 100%)",
      }}
    >
      <Stack
        justifyContent="center"
        sx={{ px: { xs: 4, md: 8 }, py: 8, color: "#fff", display: { xs: "none", md: "flex" } }}
        gap={3}
      >
        <Stack direction="row" gap={1.5} alignItems="center">
          <Box
            sx={{
              width: 46,
              height: 46,
              borderRadius: 2.5,
              display: "grid",
              placeItems: "center",
              bgcolor: "rgba(255,255,255,0.14)",
            }}
          >
            <AccountTreeIcon />
          </Box>
          <Typography variant="h3">AI Skill Analyser</Typography>
        </Stack>
        <Typography variant="h1" sx={{ maxWidth: 520, lineHeight: 1.2 }}>
          Hire on evidence, not keywords.
        </Typography>
        <Typography variant="body1" sx={{ opacity: 0.86, maxWidth: 520 }}>
          A Graph RAG recruitment platform that connects candidates, skills, technologies,
          certifications and job roles into one explainable knowledge graph.
        </Typography>
        <Stack gap={1.25} sx={{ mt: 1 }}>
          {HIGHLIGHTS.map((item) => (
            <Stack key={item} direction="row" gap={1.5} alignItems="center">
              <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: "#7c4dff" }} />
              <Typography variant="body2" sx={{ opacity: 0.9 }}>
                {item}
              </Typography>
            </Stack>
          ))}
        </Stack>
      </Stack>

      <Stack justifyContent="center" sx={{ px: { xs: 2.5, md: 6 }, py: 6 }}>
        <Card sx={{ width: "100%", maxWidth: 460, mx: "auto" }}>
          <CardContent sx={{ p: { xs: 3, md: 4 } }}>
            <Typography variant="h2">Sign in</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 3 }}>
              Use your HR workspace credentials.
            </Typography>

            {error ? (
              <Alert severity="error" sx={{ mb: 2 }}>
                {error}
              </Alert>
            ) : null}

            <Box component="form" onSubmit={handleSubmit}>
              <Stack gap={2}>
                <TextField
                  label="Work email"
                  type="email"
                  size="medium"
                  autoComplete="username"
                  required
                  fullWidth
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
                <TextField
                  label="Password"
                  type={showPassword ? "text" : "password"}
                  size="medium"
                  autoComplete="current-password"
                  required
                  fullWidth
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton
                          onClick={() => setShowPassword((value) => !value)}
                          edge="end"
                          aria-label="Toggle password visibility"
                        >
                          {showPassword ? <VisibilityOff /> : <Visibility />}
                        </IconButton>
                      </InputAdornment>
                    ),
                  }}
                />
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <FormControlLabel
                    control={
                      <Checkbox
                        size="small"
                        checked={remember}
                        onChange={(event) => setRemember(event.target.checked)}
                      />
                    }
                    label={<Typography variant="body2">Remember me</Typography>}
                  />
                  <Link component={RouterLink} to="/forgot-password" variant="body2" underline="hover">
                    Forgot password?
                  </Link>
                </Stack>
                <Button type="submit" variant="contained" size="large" disabled={submitting} fullWidth>
                  {submitting ? "Signing in…" : "Sign in"}
                </Button>
              </Stack>
            </Box>

            <Divider sx={{ my: 3 }} />
            <Typography variant="caption" color="text.secondary">
              Roles: HR Admin (full access), Recruiter (upload, search, match), Hiring Manager (read only).
            </Typography>
          </CardContent>
        </Card>
      </Stack>
    </Box>
  );
}
