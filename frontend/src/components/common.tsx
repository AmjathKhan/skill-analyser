import type { ReactNode } from "react";
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  LinearProgress,
  Skeleton,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

import { scoreColor, STATUS_COLORS } from "@/theme";

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <Stack
      direction={{ xs: "column", sm: "row" }}
      justifyContent="space-between"
      alignItems={{ xs: "flex-start", sm: "center" }}
      gap={2}
    >
      <Box>
        <Typography variant="h2">{title}</Typography>
        {subtitle ? (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {subtitle}
          </Typography>
        ) : null}
      </Box>
      {actions ? <Stack direction="row" gap={1.5} flexWrap="wrap">{actions}</Stack> : null}
    </Stack>
  );
}

export function StatCard({
  label,
  value,
  hint,
  icon,
  color = "primary.main",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  icon?: ReactNode;
  color?: string;
}) {
  return (
    <Card sx={{ height: "100%" }}>
      <CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
          <Box>
            <Typography variant="body2" color="text.secondary">
              {label}
            </Typography>
            <Typography variant="h2" sx={{ mt: 0.5 }}>
              {value}
            </Typography>
            {hint ? (
              <Typography variant="caption" color="text.secondary">
                {hint}
              </Typography>
            ) : null}
          </Box>
          {icon ? (
            <Box
              sx={{
                width: 44,
                height: 44,
                borderRadius: 2,
                display: "grid",
                placeItems: "center",
                bgcolor: (t) => t.palette.action.hover,
                color,
              }}
            >
              {icon}
            </Box>
          ) : null}
        </Stack>
      </CardContent>
    </Card>
  );
}

export function ScoreBadge({ score, size = "medium" }: { score: number; size?: "small" | "medium" }) {
  const rounded = Math.round(score);
  return (
    <Chip
      size={size === "small" ? "small" : "medium"}
      color={scoreColor(score)}
      label={`${rounded}%`}
      sx={{ fontWeight: 700 }}
    />
  );
}

export function ScoreBar({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Stack direction="row" gap={0.5} alignItems="center">
          <Typography variant="caption" color="text.secondary">
            {label}
          </Typography>
          {hint ? (
            <Tooltip title={hint}>
              <InfoOutlinedIcon sx={{ fontSize: 13, color: "text.disabled" }} />
            </Tooltip>
          ) : null}
        </Stack>
        <Typography variant="caption" fontWeight={600}>
          {Math.round(value)}%
        </Typography>
      </Stack>
      <LinearProgress
        variant="determinate"
        value={Math.max(0, Math.min(100, value))}
        color={scoreColor(value)}
        sx={{ height: 7, borderRadius: 5, mt: 0.5 }}
      />
    </Box>
  );
}

export function StatusChip({ status }: { status?: string | null }) {
  if (!status) return null;
  const label = status.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  return <Chip size="small" color={STATUS_COLORS[status] ?? "default"} label={label} variant="outlined" />;
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <Card>
      <CardContent>
        <Stack alignItems="center" gap={1.5} sx={{ py: 5, textAlign: "center" }}>
          <Typography variant="h4">{title}</Typography>
          {description ? (
            <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 520 }}>
              {description}
            </Typography>
          ) : null}
          {action}
        </Stack>
      </CardContent>
    </Card>
  );
}

export function Loading({ label = "Loading…", height = 220 }: { label?: string; height?: number }) {
  return (
    <Stack alignItems="center" justifyContent="center" gap={1.5} sx={{ height }}>
      <CircularProgress size={30} />
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
    </Stack>
  );
}

export function CardsSkeleton({ count = 4, height = 118 }: { count?: number; height?: number }) {
  return (
    <Stack direction="row" gap={2} flexWrap="wrap">
      {Array.from({ length: count }).map((_, index) => (
        <Skeleton key={index} variant="rounded" height={height} sx={{ flex: "1 1 220px", borderRadius: 3 }} />
      ))}
    </Stack>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : "Unexpected error";
  return (
    <Alert
      severity="error"
      action={
        onRetry ? (
          <Typography
            component="button"
            onClick={onRetry}
            sx={{ background: "none", border: 0, cursor: "pointer", fontWeight: 600, color: "inherit" }}
          >
            Retry
          </Typography>
        ) : undefined
      }
    >
      {message}
    </Alert>
  );
}

export function SectionCard({
  title,
  subtitle,
  action,
  children,
  minHeight,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  minHeight?: number;
}) {
  return (
    <Card sx={{ height: "100%" }}>
      <CardContent sx={{ minHeight }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1} sx={{ mb: 2 }}>
          <Box>
            <Typography variant="h4">{title}</Typography>
            {subtitle ? (
              <Typography variant="caption" color="text.secondary">
                {subtitle}
              </Typography>
            ) : null}
          </Box>
          {action}
        </Stack>
        {children}
      </CardContent>
    </Card>
  );
}
