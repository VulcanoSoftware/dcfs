"use client";

import {
  FolderOpen,
  Login,
  Wifi,
  WifiOff,
} from "@mui/icons-material";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Container,
  CssBaseline,
  FormControlLabel,
  Paper,
  Switch,
  TextField,
  ThemeProvider,
  Typography,
} from "@mui/material";
import Cookies from "js-cookie";
import Link from "next/link";
import React, { useEffect, useState } from "react";
import errors from "./error";
import FileExplorer from "./file-explorer";
import ManagerClient from "./manager-client";
import { discordTheme } from "./discord-theme";
import WebDAVClient from "./webdav-client";

interface LoginFormData {
  dcfsUrl: string;
  username: string;
  password: string;
  anonymous: boolean;
}

type SavedInfo = { dcfsUrl: string; username: string };

const SAVED_INFO_KEY = "dcfs_saved_info";
const JWT_TOKEN_KEY = "dcfs_jwt_token";

// Discord "Blurple" SVG icon
function DiscordIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
      <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057c.002.022.015.04.033.05a19.89 19.89 0 0 0 5.993 3.03.077.077 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
    </svg>
  );
}

export default function DiscordApp() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [webdavClient, setWebdavClient] = useState<WebDAVClient | null>(null);
  const [managerClient, setManagerClient] = useState<ManagerClient | null>(null);
  const [formData, setFormData] = useState<LoginFormData>({ dcfsUrl: "", username: "", password: "", anonymous: false });

  const retrieveToken = React.useCallback((): string => {
    return Cookies.get(JWT_TOKEN_KEY) ?? "";
  }, []);

  const retrieveSavedInfo = React.useCallback((): SavedInfo => {
    const raw = typeof window !== "undefined" ? localStorage.getItem(SAVED_INFO_KEY) : null;
    return raw ? (JSON.parse(raw) as SavedInfo) : { dcfsUrl: "", username: "" };
  }, []);

  const saveToken = React.useCallback((token: string) => {
    Cookies.set(JWT_TOKEN_KEY, token, { expires: 7 });
  }, []);

  const clearToken = React.useCallback(() => {
    Cookies.remove(JWT_TOKEN_KEY);
  }, []);

  const saveSavedInfo = React.useCallback((info: SavedInfo) => {
    if (typeof window !== "undefined") {
      localStorage.setItem(SAVED_INFO_KEY, JSON.stringify(info));
    }
  }, []);

  useEffect(() => {
    const token = retrieveToken();
    const savedInfo = retrieveSavedInfo();
    setFormData((prev) => ({ ...prev, dcfsUrl: savedInfo.dcfsUrl ?? "", username: savedInfo.username ?? "" }));
    if (token && savedInfo.dcfsUrl) {
      const client = new WebDAVClient(`${savedInfo.dcfsUrl}/webdav`, token, (msg) => setError(msg));
      setWebdavClient(client);
      setManagerClient(new ManagerClient(`${savedInfo.dcfsUrl}/api`, token));
      setIsLoggedIn(true);
    }
  }, [retrieveToken, retrieveSavedInfo]);

  const handleInputChange = (field: keyof LoginFormData) => (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = event.target.type === "checkbox" ? event.target.checked : event.target.value;
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleLogin = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${formData.dcfsUrl}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: formData.anonymous ? "" : formData.username, password: formData.anonymous ? "" : formData.password }),
      });
      if (!response.ok) throw new errors.CatchableError(await response.text());
      const data = await response.json();
      const token = data.token;
      saveToken(token);
      saveSavedInfo({ dcfsUrl: formData.dcfsUrl, username: formData.username });
      const client = new WebDAVClient(`${formData.dcfsUrl}/webdav`, token, (msg) => setError(msg));
      await client.connect();
      setWebdavClient(client);
      setManagerClient(new ManagerClient(`${formData.dcfsUrl}/api`, token));
      setIsLoggedIn(true);
    } catch (err) {
      if (err instanceof errors.CatchableError) {
        setError(err.message);
      } else {
        let reason = "";
        if (window.location.protocol === "https:" && !formData.dcfsUrl.startsWith("https://")) {
          reason = "URL must start with https:// when using secure connections.";
        }
        setError(`The URL is not a DCFS server, or is not reachable. ${reason}`);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleLogout = React.useCallback(() => {
    clearToken();
    setIsLoggedIn(false);
    setWebdavClient(null);
    setManagerClient(null);
    setError(null);
  }, [clearToken]);

  return (
    <ThemeProvider theme={discordTheme}>
      <CssBaseline />
      {isLoggedIn && webdavClient && managerClient ? (
        <Container maxWidth="sm" sx={{ py: 2, minHeight: "100vh" }}>
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 2 }}>
            <Typography variant="h5" component="h1" sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <FolderOpen sx={{ color: "primary.main" }} />
              DCFS Explorer
            </Typography>
            <Button variant="outlined" color="secondary" size="small" onClick={handleLogout}>Logout</Button>
          </Box>
          <FileExplorer webdavClient={webdavClient} managerClient={managerClient} />
        </Container>
      ) : (
        <Container maxWidth="sm" sx={{ py: 4, minHeight: "100vh", display: "flex", alignItems: "center" }}>
          <Paper elevation={3} sx={{ p: 4, width: "100%", bgcolor: "background.paper" }}>
            <Typography variant="h4" component="h1" gutterBottom sx={{ display: "flex", alignItems: "center", gap: 1, color: "primary.main" }} mb={3}>
              <DiscordIcon size={32} />
              Login to DCFS
            </Typography>

            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

            <Box component="div" sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <TextField label="DCFS Server URL" value={formData.dcfsUrl} onChange={handleInputChange("dcfsUrl")} placeholder="http://localhost:1900" fullWidth required disabled={isLoading} />

              <FormControlLabel control={<Switch checked={formData.anonymous} onChange={handleInputChange("anonymous")} disabled={isLoading} />}
                label={<Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                  {formData.anonymous ? <WifiOff sx={{ color: "text.primary" }} /> : <Wifi sx={{ color: "text.primary" }} />}
                  Anonymous Login
                </Box>}
              />

              {!formData.anonymous && (
                <>
                  <TextField label="Username" value={formData.username} onChange={handleInputChange("username")} fullWidth required disabled={isLoading} />
                  <TextField label="Password" type="password" value={formData.password} onChange={handleInputChange("password")} fullWidth required disabled={isLoading} />
                </>
              )}

              <Button variant="contained" onClick={handleLogin} disabled={isLoading || !formData.dcfsUrl} sx={{ mt: 2 }}
                startIcon={isLoading ? <CircularProgress size={20} /> : <Login />}>
                {isLoading ? "Connecting..." : "Connect"}
              </Button>
            </Box>

            <Box sx={{ mt: 3, pt: 2, borderTop: 1, borderColor: "divider", textAlign: "center" }}>
              <Typography variant="body2" color="text.secondary">
                Don&apos;t have DCFS running yet?{" "}
                <Link href="/getting-started" style={{ color: "#5865F2" }}>Get started →</Link>
              </Typography>
            </Box>
          </Paper>
        </Container>
      )}
    </ThemeProvider>
  );
}
