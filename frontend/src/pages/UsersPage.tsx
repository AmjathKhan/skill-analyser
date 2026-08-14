import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  MenuItem,
  Pagination,
  Stack,
  Switch,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import PersonAddIcon from "@mui/icons-material/PersonAdd";
import { useSnackbar } from "notistack";
import dayjs from "dayjs";

import { usersApi, type UserCreatePayload } from "@/api/endpoints";
import { Loading, PageHeader } from "@/components/common";
import type { User } from "@/types";

const ROLES = [
  { value: "hr_admin", label: "HR Admin" },
  { value: "recruiter", label: "Recruiter" },
  { value: "hiring_manager", label: "Hiring Manager" },
  { value: "viewer", label: "Viewer" },
];

const ROLE_COLORS: Record<string, "error" | "primary" | "info" | "default"> = {
  hr_admin: "error",
  recruiter: "primary",
  hiring_manager: "info",
  viewer: "default",
};

const EMPTY_FORM: UserCreatePayload = {
  email: "",
  full_name: "",
  password: "",
  role: "recruiter",
  department: "",
  phone: "",
  is_active: true,
  must_change_password: true,
};

export default function UsersPage() {
  const queryClient = useQueryClient();
  const { enqueueSnackbar } = useSnackbar();

  const [tab, setTab] = useState(0);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [form, setForm] = useState<UserCreatePayload>(EMPTY_FORM);
  const [auditPage, setAuditPage] = useState(1);
  const [auditAction, setAuditAction] = useState("");

  const users = useQuery({ queryKey: ["users"], queryFn: usersApi.list });

  const audit = useQuery({
    queryKey: ["audit", auditPage, auditAction],
    queryFn: () =>
      usersApi.auditLogs({ page: auditPage, page_size: 25, action: auditAction || undefined }),
    enabled: tab === 1,
  });

  const save = useMutation({
    mutationFn: () => {
      if (editing) {
        const payload: Partial<UserCreatePayload> = {
          full_name: form.full_name,
          role: form.role,
          department: form.department,
          phone: form.phone,
          is_active: form.is_active,
        };
        if (form.password) payload.password = form.password;
        return usersApi.update(editing.id, payload);
      }
      return usersApi.create(form);
    },
    onSuccess: () => {
      setOpen(false);
      setEditing(null);
      setForm(EMPTY_FORM);
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      enqueueSnackbar("User saved", { variant: "success" });
    },
    onError: (error: Error) => enqueueSnackbar(error.message, { variant: "error" }),
  });

  const toggleActive = useMutation({
    mutationFn: async (user: User) => {
      if (user.is_active) {
        await usersApi.deactivate(user.id);
        return;
      }
      await usersApi.update(user.id, { is_active: true });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      enqueueSnackbar("User updated", { variant: "success" });
    },
    onError: (error: Error) => enqueueSnackbar(error.message, { variant: "error" }),
  });

  const totalAuditPages = audit.data
    ? Math.max(1, Math.ceil(audit.data.meta.total / audit.data.meta.page_size))
    : 1;

  return (
    <>
      <PageHeader
        title="Users & audit"
        subtitle="Manage HR accounts, roles and permissions, and review every action taken on the platform."
        actions={
          <Button
            variant="contained"
            startIcon={<PersonAddIcon />}
            onClick={() => {
              setEditing(null);
              setForm(EMPTY_FORM);
              setOpen(true);
            }}
          >
            Add user
          </Button>
        }
      />

      <Card>
        <Tabs
          value={tab}
          onChange={(_event, value) => setTab(value)}
          sx={{ px: 2, borderBottom: "1px solid", borderColor: "divider" }}
        >
          <Tab label="Users" />
          <Tab label="Audit log" />
        </Tabs>

        <CardContent>
          {tab === 0 ? (
            users.isLoading ? (
              <Loading label="Loading users…" />
            ) : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Name</TableCell>
                    <TableCell>Email</TableCell>
                    <TableCell>Role</TableCell>
                    <TableCell>Department</TableCell>
                    <TableCell>Last login</TableCell>
                    <TableCell align="center">Active</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(users.data ?? []).map((user) => (
                    <TableRow key={user.id} hover>
                      <TableCell>{user.full_name}</TableCell>
                      <TableCell>{user.email}</TableCell>
                      <TableCell>
                        <Chip size="small" color={ROLE_COLORS[user.role] ?? "default"} label={user.role_label} />
                      </TableCell>
                      <TableCell>{user.department ?? "—"}</TableCell>
                      <TableCell>
                        {user.last_login_at ? dayjs(user.last_login_at).format("DD MMM YY HH:mm") : "never"}
                      </TableCell>
                      <TableCell align="center">
                        <Switch
                          size="small"
                          checked={user.is_active}
                          onChange={() => toggleActive.mutate(user)}
                        />
                      </TableCell>
                      <TableCell align="right">
                        <Button
                          size="small"
                          onClick={() => {
                            setEditing(user);
                            setForm({
                              email: user.email,
                              full_name: user.full_name,
                              password: "",
                              role: user.role,
                              department: user.department ?? "",
                              phone: user.phone ?? "",
                              is_active: user.is_active,
                            });
                            setOpen(true);
                          }}
                        >
                          Edit
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )
          ) : null}

          {tab === 1 ? (
            <>
              <TextField
                size="small"
                label="Filter by action"
                value={auditAction}
                onChange={(event) => {
                  setAuditAction(event.target.value);
                  setAuditPage(1);
                }}
                sx={{ mb: 2, minWidth: 260 }}
              />
              {audit.isLoading ? (
                <Loading label="Loading audit log…" />
              ) : (
                <>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>When</TableCell>
                        <TableCell>Actor</TableCell>
                        <TableCell>Action</TableCell>
                        <TableCell>Entity</TableCell>
                        <TableCell>Description</TableCell>
                        <TableCell>IP</TableCell>
                        <TableCell>Status</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {(audit.data?.items ?? []).map((item) => (
                        <TableRow key={item.id} hover>
                          <TableCell>{dayjs(item.created_at).format("DD MMM HH:mm:ss")}</TableCell>
                          <TableCell>{item.actor}</TableCell>
                          <TableCell>
                            <Chip size="small" variant="outlined" label={item.action} />
                          </TableCell>
                          <TableCell>
                            {item.entity_type ? `${item.entity_type}#${item.entity_id ?? "-"}` : "—"}
                          </TableCell>
                          <TableCell>{item.description ?? "—"}</TableCell>
                          <TableCell>{item.ip_address ?? "—"}</TableCell>
                          <TableCell>
                            <Chip
                              size="small"
                              color={item.status === "success" ? "success" : "error"}
                              label={item.status}
                            />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <Stack alignItems="center" sx={{ mt: 2 }}>
                    <Pagination
                      page={auditPage}
                      count={totalAuditPages}
                      onChange={(_event, value) => setAuditPage(value)}
                      color="primary"
                    />
                  </Stack>
                </>
              )}
            </>
          ) : null}
        </CardContent>
      </Card>

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editing ? `Edit ${editing.full_name}` : "Add user"}</DialogTitle>
        <DialogContent dividers>
          <Grid container spacing={2} sx={{ pt: 1 }}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Full name"
                value={form.full_name}
                onChange={(event) => setForm({ ...form, full_name: event.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Email"
                type="email"
                disabled={Boolean(editing)}
                value={form.email}
                onChange={(event) => setForm({ ...form, email: event.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                select
                label="Role"
                value={form.role}
                onChange={(event) => setForm({ ...form, role: event.target.value })}
              >
                {ROLES.map((role) => (
                  <MenuItem key={role.value} value={role.value}>
                    {role.label}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label={editing ? "New password (optional)" : "Password"}
                type="password"
                value={form.password}
                onChange={(event) => setForm({ ...form, password: event.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Department"
                value={form.department}
                onChange={(event) => setForm({ ...form, department: event.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Phone"
                value={form.phone}
                onChange={(event) => setForm({ ...form, phone: event.target.value })}
              />
            </Grid>
            <Grid item xs={12}>
              <Stack direction="row" alignItems="center" gap={1}>
                <Switch
                  checked={form.is_active ?? true}
                  onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
                />
                <Typography variant="body2">Active</Typography>
              </Stack>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={
              save.isPending ||
              form.full_name.trim().length < 2 ||
              (!editing && (form.email.trim().length < 5 || form.password.length < 8))
            }
            onClick={() => save.mutate()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
