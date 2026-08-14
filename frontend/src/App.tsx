import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Box, CircularProgress } from "@mui/material";

import AppLayout from "@/components/AppLayout";
import { useAuth } from "@/auth/AuthContext";

const LoginPage = lazy(() => import("@/pages/LoginPage"));
const ForgotPasswordPage = lazy(() => import("@/pages/ForgotPasswordPage"));
const DashboardPage = lazy(() => import("@/pages/DashboardPage"));
const UploadPage = lazy(() => import("@/pages/UploadPage"));
const CandidatesPage = lazy(() => import("@/pages/CandidatesPage"));
const CandidateProfilePage = lazy(() => import("@/pages/CandidateProfilePage"));
const SkillMatchPage = lazy(() => import("@/pages/SkillMatchPage"));
const SearchPage = lazy(() => import("@/pages/SearchPage"));
const GraphPage = lazy(() => import("@/pages/GraphPage"));
const SkillsPage = lazy(() => import("@/pages/SkillsPage"));
const JobsPage = lazy(() => import("@/pages/JobsPage"));
const ReportsPage = lazy(() => import("@/pages/ReportsPage"));
const UsersPage = lazy(() => import("@/pages/UsersPage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));
const NotFoundPage = lazy(() => import("@/pages/NotFoundPage"));

function FullScreenLoader() {
  return (
    <Box sx={{ display: "grid", placeItems: "center", minHeight: "100vh" }}>
      <CircularProgress />
    </Box>
  );
}

function RequireAuth({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <FullScreenLoader />;
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  return children;
}

export default function App() {
  return (
    <Suspense fallback={<FullScreenLoader />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route
          element={
            <RequireAuth>
              <AppLayout />
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/candidates" element={<CandidatesPage />} />
          <Route path="/candidates/:candidateId" element={<CandidateProfilePage />} />
          <Route path="/skill-match" element={<SkillMatchPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/skills" element={<SkillsPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/users" element={<UsersPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
