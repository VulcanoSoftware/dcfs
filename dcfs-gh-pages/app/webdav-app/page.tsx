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
  FormControlLabel,
  Paper,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import Cookies from "js-cookie";
import React, { useEffect, useState } from "react";
import errors from "./error";
import FileExplorer from "./file-explorer";
import ManagerClient from "./manager-client";
import WebDAVClient from "./webdav-client";

interface LoginFormData {
  dcfsUrl: string;
  username: string;
  password: string;
  anonymous: boolean;
}

type SavedInfo = {
  dcfsUrl: string;
  username: string;
};

const SAVED_INFO_KEY = "saved_info";
const JWT_TOKEN_KEY = "jwt_token";

export default function WebDAVApp() {
  // State management
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [webdavClient, setWebdavClient] = useState<WebDAVClient | null>(null);
  const [managerClient, setManagerClient] = useState<ManagerClient | null>(
    null
  );
  const [formData, setFormData] = useState<LoginFormData>({
    dcfsUrl: "",
    username: "",
    password: "",
    anonymous: false,
  });

  const handleError = (message: string) => {
    setError(message);
  };

  const retrieveToken = React.useCallback(async (): Promise<string> => {
    const retrievedString = Cookies.get(JWT_TOKEN_KEY);
    return retrievedString ?? "";
  }, []);

  const retrieveSavedInfo = React.useCallback(async (): Promise<SavedInfo> => {
    const retrievedString = localStorage.getItem(SAVED_INFO_KEY);
    return retrievedString
      ? (JSON.parse(retrievedString) as SavedInfo)
      : {
          dcfsUrl: "",
          username: "",
        };
  }, []);

  const clearToken = React.useCallback(async () => {
    Cookies.remove(JWT_TOKEN_KEY);
  }, []);

  const saveToken = React.useCallback(async (token: string) => {
    Cookies.set(JWT_TOKEN_KEY, token);
  }, []);

  const saveSavedInfo = React.useCallback(
    async (savedInfo: SavedInfo) => {
      localStorage.setItem(SAVED_INFO_KEY, JSON.stringify(savedInfo));
    },
    []
  );

  // Restore session on mount
  useEffect(() => {
    const restoreSession = async () => {
      const token = await retrieveToken();
      const savedInfo = await retrieveSavedInfo();

      setFormData((prev) => ({
        ...prev,
        dcfsUrl: savedInfo.dcfsUrl ?? "",
        username: savedInfo.username ?? "",
      }));

      if (token && savedInfo.dcfsUrl) {
        const client = new WebDAVClient(
          `${savedInfo.dcfsUrl}/webdav`,
          token,
          handleError
        );
        setWebdavClient(client);

        const managerClient = new ManagerClient(
          `${savedInfo.dcfsUrl}/api`,
          token
        );
        setManagerClient(managerClient);

        setIsLoggedIn(true);
      }
    };

    restoreSession();
  }, [retrieveToken, retrieveSavedInfo]);

  const handleInputChange =
    (field: keyof LoginFormData) =>
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const value =
        event.target.type === "checkbox"
          ? event.target.checked
          : event.target.value;
      setFormData((prev) => ({ ...prev, [field]: value }));
    };

  const handleLogin = async () => {
    setIsLoading(true);
    setError(null);

    try {
      // Send login request to get JWT token
      const response = await fetch(`${formData.dcfsUrl}/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username: formData.anonymous ? "" : formData.username,
          password: formData.anonymous ? "" : formData.password,
        }),
      });

      if (!response.ok) {
        throw new errors.CatchableError(await response.text());
      }

      const data = await response.json();
      const token = data.token;

      // Store JWT token in cookies
      await saveToken(token);

      await saveSavedInfo({
        dcfsUrl: formData.dcfsUrl,
        username: formData.username,
      });

      // Create WebDAV client with JWT token
      const client = new WebDAVClient(
        `${formData.dcfsUrl}/webdav`,
        token,
        handleError
      );
      await client.connect();
      setWebdavClient(client);

      const managerClient = new ManagerClient(`${formData.dcfsUrl}/api`, token);
      setManagerClient(managerClient);

      setIsLoggedIn(true);
    } catch (err) {
      if (err instanceof errors.CatchableError) {
        setError(err.message);
      } else {
        let potentialReason = "";
        if (
          window.location.protocol === "https:" &&
          !formData.dcfsUrl.startsWith("https://")
        ) {
          potentialReason =
            "URL must start with https:// when using secure connections.";
        }
        setError(
          `The URL is not a dcfs server, or is not reachable. ${potentialReason}`
        );
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleLogout = React.useCallback(async () => {
    await clearToken();
    setIsLoggedIn(false);
    setWebdavClient(null);
    setManagerClient(null);
    setError(null);
  }, [clearToken]);

  return (
    <>
      {isLoggedIn && webdavClient && managerClient ? (
        <Container maxWidth="sm" sx={{ py: 2, minHeight: "100vh" }}>
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              mb: 2,
            }}
          >
            <Typography
              variant="h5"
              component="h1"
              sx={{ display: "flex", alignItems: "center", gap: 1 }}
            >
              <FolderOpen sx={{ color: "text.primary" }} />
              dcfs Explorer
            </Typography>
            <Button
              variant="outlined"
              color="secondary"
              size="small"
              onClick={handleLogout}
            >
              Logout
            </Button>
          </Box>
          <FileExplorer
            webdavClient={webdavClient}
            managerClient={managerClient}
          />
        </Container>
      ) : (
        <Container
          maxWidth="sm"
          sx={{
            py: 4,
            minHeight: "100vh",
            display: "flex",
            alignItems: "center",
          }}
        >
          <Paper elevation={3} sx={{ p: 4, width: "100%" }}>
            <Typography
              variant="h4"
              component="h1"
              gutterBottom
              sx={{ display: "flex", alignItems: "center", gap: 1 }}
              mb={3}
            >
              <Login sx={{ color: "text.primary" }} />
              Login to dcfs
            </Typography>

            {error && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {error}
              </Alert>
            )}

            <Box
              component="form"
              sx={{ display: "flex", flexDirection: "column", gap: 2 }}
            >
              <TextField
                label="dcfs Server URL (without /webdav suffix)"
                value={formData.dcfsUrl}
                onChange={handleInputChange("dcfsUrl")}
                placeholder="localhost or your-server.com"
                fullWidth
                required
                disabled={isLoading}
              />

              <FormControlLabel
                control={
                  <Switch
                    checked={formData.anonymous}
                    onChange={handleInputChange("anonymous")}
                    disabled={isLoading}
                  />
                }
                label={
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    {formData.anonymous ? (
                      <WifiOff sx={{ color: "text.primary" }} />
                    ) : (
                      <Wifi sx={{ color: "text.primary" }} />
                    )}
                    Anonymous Login
                  </Box>
                }
              />

              {!formData.anonymous && (
                <>
                  <TextField
                    label="Username"
                    value={formData.username}
                    onChange={handleInputChange("username")}
                    fullWidth
                    required
                    disabled={isLoading}
                  />

                  <TextField
                    label="Password"
                    type="password"
                    value={formData.password}
                    onChange={handleInputChange("password")}
                    fullWidth
                    required
                    disabled={isLoading}
                  />
                </>
              )}

              <Button
                variant="contained"
                onClick={handleLogin}
                disabled={isLoading || !formData.dcfsUrl}
                sx={{ mt: 2 }}
                startIcon={
                  isLoading ? <CircularProgress size={20} /> : <Login />
                }
              >
                {isLoading ? "Connecting..." : "Connect"}
              </Button>
            </Box>
          </Paper>
        </Container>
      )}
    </>
  );
}
