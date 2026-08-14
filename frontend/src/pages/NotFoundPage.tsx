import { Link as RouterLink } from "react-router-dom";
import { Box, Button, Stack, Typography } from "@mui/material";

export default function NotFoundPage() {
  return (
    <Box sx={{ display: "grid", placeItems: "center", minHeight: "100vh", p: 3 }}>
      <Stack alignItems="center" gap={2} textAlign="center">
        <Typography variant="h1" sx={{ fontSize: 72, fontWeight: 800, color: "primary.main" }}>
          404
        </Typography>
        <Typography variant="h3">This page does not exist</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 440 }}>
          The link may be outdated or the record was removed. Head back to the dashboard to continue.
        </Typography>
        <Button component={RouterLink} to="/dashboard" variant="contained">
          Back to dashboard
        </Button>
      </Stack>
    </Box>
  );
}
