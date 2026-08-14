import { Component, type ErrorInfo, type ReactNode } from "react";
import { Alert, AlertTitle, Box, Button, Stack, Typography } from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";

interface Props {
  children: ReactNode;
  /** Changing this value clears the error, e.g. when the route changes. */
  resetKey?: unknown;
}

interface State {
  error: Error | null;
}

/** Keeps a render failure inside the page instead of blanking the whole app. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidUpdate(previous: Props): void {
    if (this.state.error && previous.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Unhandled render error", error, info.componentStack);
  }

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <Box sx={{ py: 2 }}>
        <Alert severity="error">
          <AlertTitle>Something went wrong on this page</AlertTitle>
          <Typography variant="body2">
            The rest of the app is still usable. If this keeps happening, share the message below with
            your administrator.
          </Typography>
          <Typography variant="caption" component="pre" sx={{ mt: 1, whiteSpace: "pre-wrap" }}>
            {error.message}
          </Typography>
          <Stack direction="row" gap={1} sx={{ mt: 1.5 }}>
            <Button size="small" variant="outlined" startIcon={<RefreshIcon />} onClick={() => this.setState({ error: null })}>
              Try again
            </Button>
            <Button size="small" onClick={() => window.location.reload()}>
              Reload
            </Button>
          </Stack>
        </Alert>
      </Box>
    );
  }
}
