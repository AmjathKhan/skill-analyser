import { useMemo, useState } from "react";
import { Link as RouterLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  AppBar,
  Avatar,
  Box,
  Chip,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  ListSubheader,
  Menu,
  MenuItem,
  Stack,
  Toolbar,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import AssessmentIcon from "@mui/icons-material/Assessment";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import DashboardIcon from "@mui/icons-material/Dashboard";
import GroupIcon from "@mui/icons-material/Group";
import LightModeIcon from "@mui/icons-material/LightMode";
import LogoutIcon from "@mui/icons-material/Logout";
import MenuIcon from "@mui/icons-material/Menu";
import PeopleAltIcon from "@mui/icons-material/PeopleAlt";
import PsychologyIcon from "@mui/icons-material/Psychology";
import SearchIcon from "@mui/icons-material/Search";
import SettingsIcon from "@mui/icons-material/Settings";
import SchemaIcon from "@mui/icons-material/Schema";
import WorkIcon from "@mui/icons-material/Work";

import { useAuth } from "@/auth/AuthContext";
import { useColorMode } from "@/ColorMode";
import ErrorBoundary from "@/components/ErrorBoundary";

const DRAWER_WIDTH = 264;

interface NavItem {
  label: string;
  to: string;
  icon: React.ReactNode;
  permission?: string;
  adminOnly?: boolean;
}

const NAV_SECTIONS: { heading: string; items: NavItem[] }[] = [
  {
    heading: "Overview",
    items: [
      { label: "Dashboard", to: "/dashboard", icon: <DashboardIcon /> },
      { label: "Reports", to: "/reports", icon: <AssessmentIcon />, permission: "report:read" },
    ],
  },
  {
    heading: "Talent",
    items: [
      { label: "Upload Resumes", to: "/upload", icon: <CloudUploadIcon />, permission: "resume:upload" },
      { label: "Candidates", to: "/candidates", icon: <PeopleAltIcon /> },
      { label: "Search", to: "/search", icon: <SearchIcon />, permission: "search:run" },
      { label: "Skill Match", to: "/skill-match", icon: <PsychologyIcon />, permission: "match:run" },
      { label: "Job Requirements", to: "/jobs", icon: <WorkIcon />, permission: "match:run" },
    ],
  },
  {
    heading: "Knowledge",
    items: [
      { label: "Knowledge Graph", to: "/graph", icon: <AccountTreeIcon />, permission: "graph:read" },
      { label: "Skills Knowledge Base", to: "/skills", icon: <SchemaIcon />, permission: "graph:read" },
    ],
  },
  {
    heading: "Administration",
    items: [
      { label: "Users & Audit", to: "/users", icon: <GroupIcon />, adminOnly: true },
      { label: "Settings", to: "/settings", icon: <SettingsIcon /> },
    ],
  },
];

export default function AppLayout() {
  const theme = useTheme();
  const isDesktop = useMediaQuery(theme.breakpoints.up("lg"));
  const [mobileOpen, setMobileOpen] = useState(false);
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const { user, logout, can, isAdmin } = useAuth();
  const { mode, toggle } = useColorMode();
  const location = useLocation();
  const navigate = useNavigate();

  const sections = useMemo(
    () =>
      NAV_SECTIONS.map((section) => ({
        ...section,
        items: section.items.filter(
          (item) => (!item.permission || can(item.permission)) && (!item.adminOnly || isAdmin),
        ),
      })).filter((section) => section.items.length > 0),
    [can, isAdmin],
  );

  const currentTitle = useMemo(() => {
    const all = NAV_SECTIONS.flatMap((section) => section.items);
    return all.find((item) => location.pathname.startsWith(item.to))?.label ?? "AI Skill Analyser";
  }, [location.pathname]);

  const drawer = (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <Toolbar sx={{ gap: 1.5, px: 2.5 }}>
        <Box
          sx={{
            width: 36,
            height: 36,
            borderRadius: 2,
            display: "grid",
            placeItems: "center",
            background: "linear-gradient(135deg,#1a73e8,#7c4dff)",
            color: "#fff",
          }}
        >
          <AccountTreeIcon fontSize="small" />
        </Box>
        <Box>
          <Typography variant="subtitle1" fontWeight={700} lineHeight={1.2}>
            Skill Analyser
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Graph RAG Recruiting
          </Typography>
        </Box>
      </Toolbar>
      <Divider />
      <Box sx={{ flex: 1, overflowY: "auto", px: 1.5, py: 1 }}>
        {sections.map((section) => (
          <List
            key={section.heading}
            dense
            subheader={
              <ListSubheader disableSticky sx={{ bgcolor: "transparent", fontSize: 11, letterSpacing: 1 }}>
                {section.heading.toUpperCase()}
              </ListSubheader>
            }
          >
            {section.items.map((item) => {
              const selected = location.pathname.startsWith(item.to);
              return (
                <ListItemButton
                  key={item.to}
                  component={RouterLink}
                  to={item.to}
                  selected={selected}
                  onClick={() => setMobileOpen(false)}
                  sx={{ mb: 0.25 }}
                >
                  <ListItemIcon sx={{ minWidth: 38, color: selected ? "primary.main" : undefined }}>
                    {item.icon}
                  </ListItemIcon>
                  <ListItemText
                    primary={item.label}
                    primaryTypographyProps={{ fontSize: 14, fontWeight: selected ? 600 : 500 }}
                  />
                </ListItemButton>
              );
            })}
          </List>
        ))}
      </Box>
      <Divider />
      <Box sx={{ p: 2 }}>
        <Chip
          size="small"
          color="primary"
          variant="outlined"
          label={user?.role_label ?? "Signed in"}
          sx={{ width: "100%" }}
        />
      </Box>
    </Box>
  );

  return (
    <Box sx={{ display: "flex", minHeight: "100vh", bgcolor: "background.default" }}>
      <AppBar
        position="fixed"
        color="inherit"
        sx={{
          width: { lg: `calc(100% - ${DRAWER_WIDTH}px)` },
          ml: { lg: `${DRAWER_WIDTH}px` },
          borderBottom: "1px solid",
          borderColor: "divider",
          backdropFilter: "blur(8px)",
          backgroundColor: (t) =>
            t.palette.mode === "light" ? "rgba(255,255,255,0.85)" : "rgba(18,26,46,0.85)",
        }}
        elevation={0}
      >
        <Toolbar sx={{ gap: 1 }}>
          <IconButton
            edge="start"
            onClick={() => setMobileOpen(true)}
            sx={{ display: { lg: "none" } }}
            aria-label="Open navigation"
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h4" sx={{ flexGrow: 1 }}>
            {currentTitle}
          </Typography>
          <Tooltip title={mode === "light" ? "Dark mode" : "Light mode"}>
            <IconButton onClick={toggle} aria-label="Toggle colour mode">
              {mode === "light" ? <DarkModeIcon /> : <LightModeIcon />}
            </IconButton>
          </Tooltip>
          <Tooltip title={user?.email ?? ""}>
            <IconButton onClick={(event) => setAnchor(event.currentTarget)} aria-label="Account menu">
              <Avatar sx={{ width: 34, height: 34, bgcolor: "primary.main", fontSize: 15 }}>
                {user?.full_name?.charAt(0).toUpperCase() ?? "?"}
              </Avatar>
            </IconButton>
          </Tooltip>
          <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
            <Box sx={{ px: 2, py: 1.25 }}>
              <Typography variant="subtitle2">{user?.full_name}</Typography>
              <Typography variant="caption" color="text.secondary">
                {user?.email}
              </Typography>
            </Box>
            <Divider />
            <MenuItem
              onClick={() => {
                setAnchor(null);
                navigate("/settings");
              }}
            >
              <ListItemIcon>
                <SettingsIcon fontSize="small" />
              </ListItemIcon>
              Settings
            </MenuItem>
            <MenuItem
              onClick={async () => {
                setAnchor(null);
                await logout();
                navigate("/login");
              }}
            >
              <ListItemIcon>
                <LogoutIcon fontSize="small" />
              </ListItemIcon>
              Sign out
            </MenuItem>
          </Menu>
        </Toolbar>
      </AppBar>

      <Box component="nav" sx={{ width: { lg: DRAWER_WIDTH }, flexShrink: { lg: 0 } }}>
        <Drawer
          variant={isDesktop ? "permanent" : "temporary"}
          open={isDesktop || mobileOpen}
          onClose={() => setMobileOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{
            "& .MuiDrawer-paper": {
              width: DRAWER_WIDTH,
              boxSizing: "border-box",
              borderRight: "1px solid",
              borderColor: "divider",
            },
          }}
        >
          {drawer}
        </Drawer>
      </Box>

      <Box component="main" sx={{ flexGrow: 1, width: { lg: `calc(100% - ${DRAWER_WIDTH}px)` } }}>
        <Toolbar />
        <Stack sx={{ p: { xs: 2, md: 3 }, gap: 3 }}>
          <ErrorBoundary resetKey={location.pathname}>
            <Outlet />
          </ErrorBoundary>
        </Stack>
      </Box>
    </Box>
  );
}
