import { alpha, createTheme, type ThemeOptions } from "@mui/material/styles";

const BRAND = "#1a73e8";
const ACCENT = "#7c4dff";

const shared: ThemeOptions = {
  shape: { borderRadius: 12 },
  typography: {
    fontFamily: "'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif",
    h1: { fontSize: "2rem", fontWeight: 700, letterSpacing: "-0.02em" },
    h2: { fontSize: "1.6rem", fontWeight: 700, letterSpacing: "-0.02em" },
    h3: { fontSize: "1.35rem", fontWeight: 600 },
    h4: { fontSize: "1.15rem", fontWeight: 600 },
    h5: { fontSize: "1rem", fontWeight: 600 },
    h6: { fontSize: "0.925rem", fontWeight: 600 },
    button: { textTransform: "none", fontWeight: 600 },
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: { root: { borderRadius: 10, paddingInline: 18 } },
    },
    MuiCard: {
      styleOverrides: {
        root: { borderRadius: 16, border: "1px solid", borderColor: "rgba(148,163,184,0.22)" },
      },
      defaultProps: { elevation: 0 },
    },
    MuiPaper: { defaultProps: { elevation: 0 } },
    MuiChip: { styleOverrides: { root: { fontWeight: 500, borderRadius: 8 } } },
    MuiTextField: { defaultProps: { size: "small" } },
    MuiSelect: { defaultProps: { size: "small" } },
    MuiTooltip: { defaultProps: { arrow: true } },
    MuiTableCell: { styleOverrides: { head: { fontWeight: 600 } } },
    MuiListItemButton: { styleOverrides: { root: { borderRadius: 10 } } },
  },
};

export function buildTheme(mode: "light" | "dark") {
  return createTheme({
    ...shared,
    palette: {
      mode,
      primary: { main: BRAND },
      secondary: { main: ACCENT },
      success: { main: "#12b76a" },
      warning: { main: "#f79009" },
      error: { main: "#f04438" },
      info: { main: "#0ea5e9" },
      background:
        mode === "light"
          ? { default: "#f6f8fc", paper: "#ffffff" }
          : { default: "#0b1020", paper: "#121a2e" },
      divider: mode === "light" ? alpha("#94a3b8", 0.22) : alpha("#94a3b8", 0.18),
    },
  });
}

/** Consistent colours for graph node labels and score bands. */
export const NODE_COLORS: Record<string, string> = {
  Candidate: "#1a73e8",
  Skill: "#12b76a",
  Technology: "#7c4dff",
  Company: "#f79009",
  Certification: "#e11d48",
  Project: "#06b6d4",
  Education: "#8b5cf6",
  JobRole: "#0891b2",
  Category: "#64748b",
  Department: "#94a3b8",
};

export function scoreColor(score: number): "success" | "info" | "warning" | "error" {
  if (score >= 85) return "success";
  if (score >= 70) return "info";
  if (score >= 50) return "warning";
  return "error";
}

export const STATUS_COLORS: Record<string, "default" | "primary" | "success" | "warning" | "error" | "info"> = {
  new: "default",
  pending_review: "warning",
  reviewed: "info",
  shortlisted: "success",
  interviewing: "info",
  offered: "primary",
  hired: "success",
  rejected: "error",
  on_hold: "warning",
  archived: "default",
};
