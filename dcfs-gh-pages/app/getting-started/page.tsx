"use client";

import { ArrowBack, Settings } from "@mui/icons-material";
import {
  Box,
  Button,
  Step,
  StepContent,
  StepLabel,
  Stepper,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import Link from "next/link";
import { useState, useEffect } from "react";

export default function GettingStarted() {
  const [activeStep, setActiveStep] = useState(0);
  const [pathStyle, setPathStyle] = useState<"unix" | "windows">("unix");
  const [dockerConfig, setDockerConfig] = useState({
    dcfsPort: 1900,
    dcfsDataDir: "/home/user/.dcfs",
  });

  // Auto-detect OS and set default path style
  useEffect(() => {
    if (typeof window !== "undefined") {
      const userAgent = window.navigator.userAgent;
      const isWindows = userAgent.includes("Windows");
      setPathStyle(isWindows ? "windows" : "unix");

      // Set default path based on OS
      setDockerConfig((prev) => ({
        ...prev,
        dcfsDataDir: isWindows
          ? "C:\\Users\\user\\.dcfs"
          : "/home/user/.dcfs",
      }));
    }
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800">
      <div className="container mx-auto px-6 py-12 max-w-4xl">
        <header className="text-center mb-12">
          <Link
            href="/"
            className="inline-flex items-center text-slate-400 hover:text-white mb-6 transition-colors"
          >
            <ArrowBack className="w-5 h-5 mr-2" />
            Back to Home
          </Link>
          <h1 className="text-4xl font-bold text-white mb-4">
            Getting Started with dcfs
          </h1>
          <p className="text-xl text-slate-300">
            Follow these steps to set up your Discord File System
          </p>
        </header>

        <div className="bg-slate-800 rounded-xl p-8 shadow-lg border border-slate-700">
          <Stepper activeStep={activeStep} orientation="vertical">
            <Step>
              <StepLabel
                onClick={() => setActiveStep(0)}
                sx={{ cursor: "pointer" }}
              >
                <Typography variant="h6" className="text-white">
                  Create a Discord Bot
                </Typography>
              </StepLabel>
              <StepContent>
                <Typography className="text-slate-300" sx={{ marginBottom: 3 }}>
                  First, create a Discord bot and get its token. Follow these
                  steps at the{" "}
                  <a
                    href="https://discord.com/developers/applications"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-500 hover:text-blue-600 underline"
                  >
                    Discord Developer Portal
                  </a>
                  :
                </Typography>
                <ol
                  className="list-decimal list-inside text-slate-300"
                  style={{ marginBottom: "24px" }}
                >
                  <li style={{ marginBottom: "12px" }}>
                    Go to{" "}
                    <a
                      href="https://discord.com/developers/applications"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-500 hover:text-blue-600 underline"
                    >
                      Discord Developer Portal
                    </a>
                  </li>
                  <li style={{ marginBottom: "12px" }}>
                    Click <b>&quot;New Application&quot;</b> and give it a name
                  </li>
                  <li style={{ marginBottom: "12px" }}>
                    Go to the <b>&quot;Bot&quot;</b> section and click <b>&quot;Add Bot&quot;</b>
                  </li>
                  <li style={{ marginBottom: "12px" }}>
                    Under the <b>&quot;Privileged Gateway Intents&quot;</b> section, enable{" "}
                    <b>&quot;Message Content Intent&quot;</b> and <b>&quot;Server Members Intent&quot;</b>
                  </li>
                  <li style={{ marginBottom: "12px" }}>
                    Click <b>&quot;Reset Token&quot;</b> or <b>&quot;Copy&quot;</b> to get your bot token
                  </li>
                </ol>
                <div style={{ marginTop: "24px" }}>
                  <Button
                    variant="contained"
                    onClick={() => setActiveStep(1)}
                    sx={{ mr: 1 }}
                  >
                    Continue
                  </Button>
                </div>
              </StepContent>
            </Step>

            <Step>
              <StepLabel
                onClick={() => setActiveStep(1)}
                sx={{ cursor: "pointer" }}
              >
                <Typography variant="h6" className="text-white">
                  Create a Private Channel & Invite Your Bot
                </Typography>
              </StepLabel>
              <StepContent>
                <Typography className="text-slate-300" sx={{ marginBottom: 3 }}>
                  Create a private Discord channel and add your bot to it.
                </Typography>
                <ol
                  className="list-decimal list-inside text-slate-300"
                  style={{ marginBottom: "24px" }}
                >
                  <li style={{ marginBottom: "12px" }}>
                    Create a new Discord server (or use an existing one)
                  </li>
                  <li style={{ marginBottom: "12px" }}>
                    Enable Developer Mode:{" "}
                    <b>Settings → Advanced → Developer Mode</b>
                  </li>
                  <li style={{ marginBottom: "12px" }}>
                    Create a private text channel for storing files
                  </li>
                  <li style={{ marginBottom: "12px" }}>
                    Invite your bot to the server using this URL (replace
                    CLIENT_ID with your app&apos;s client ID):<br />
                    <code className="bg-slate-700 px-2 py-1 rounded text-sm break-all">
                      https://discord.com/api/oauth2/authorize?client_id=CLIENT_ID&permissions=8&scope=bot
                    </code>
                  </li>
                  <li style={{ marginBottom: "12px" }}>
                    Right-click your channel → <b>Copy ID</b> to get the channel ID
                  </li>
                  <li style={{ marginBottom: "12px" }}>
                    Right-click the server name → <b>Copy ID</b> to get the guild (server) ID
                  </li>
                </ol>
                <div style={{ marginTop: "24px" }}>
                  <Button
                    variant="contained"
                    onClick={() => setActiveStep(2)}
                    sx={{ mr: 1 }}
                  >
                    Continue
                  </Button>
                </div>
              </StepContent>
            </Step>

            <Step>
              <StepLabel
                onClick={() => setActiveStep(2)}
                sx={{ cursor: "pointer" }}
              >
                <Typography variant="h6" className="text-white">
                  Generate Configuration
                </Typography>
              </StepLabel>
              <StepContent>
                <Typography className="text-slate-300" sx={{ marginBottom: 3 }}>
                  Use our config generator to create your dcfs configuration
                  file with your bot token, guild ID, and channel IDs.
                </Typography>
                <div style={{ marginBottom: "24px" }}>
                  <Link
                    href="/config-generator"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                  >
                    <Settings className="w-5 h-5 mr-2" />
                    Open Config Generator
                  </Link>
                </div>
                <div style={{ marginTop: "24px" }}>
                  <Button
                    variant="contained"
                    onClick={() => setActiveStep(3)}
                    sx={{ mr: 1 }}
                  >
                    Continue
                  </Button>
                </div>
              </StepContent>
            </Step>

            <Step>
              <StepLabel
                onClick={() => setActiveStep(3)}
                sx={{ cursor: "pointer" }}
              >
                <Typography variant="h6" className="text-white">
                  Run dcfs Server
                </Typography>
              </StepLabel>
              <StepContent>
                <Typography className="text-slate-300" sx={{ marginBottom: 3 }}>
                  Run dcfs with Docker (recommended):
                </Typography>

                <Box
                  sx={{
                    marginBottom: 3,
                    display: "flex",
                    gap: 2,
                    flexDirection: "column",
                  }}
                >
                  <Box sx={{ display: "flex", gap: 4 }}>
                    <TextField
                      label="dcfs Port"
                      type="number"
                      value={dockerConfig.dcfsPort}
                      onChange={(e) =>
                        setDockerConfig((prev) => ({
                          ...prev,
                          dcfsPort: parseInt(e.target.value) || 1900,
                        }))
                      }
                    />
                    <TextField
                      label="Path of .dcfs directory"
                      value={dockerConfig.dcfsDataDir}
                      onChange={(e) =>
                        setDockerConfig((prev) => ({
                          ...prev,
                          dcfsDataDir: e.target.value,
                        }))
                      }
                      slotProps={{
                        input: {
                          endAdornment: (
                            <span className="text-slate-400">
                              {pathStyle === "windows"
                                ? "\\config.yaml"
                                : "/config.yaml"}
                            </span>
                          ),
                        },
                      }}
                      sx={{ flex: 1 }}
                    />
                  </Box>

                  <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
                    <Typography variant="body2" color="text.secondary">
                      Path Style:
                    </Typography>
                    <ToggleButtonGroup
                      value={pathStyle}
                      exclusive
                      onChange={(_, newStyle) => {
                        if (newStyle) {
                          setPathStyle(newStyle);
                          setDockerConfig((prev) => ({
                            ...prev,
                            dcfsDataDir:
                              newStyle === "windows"
                                ? "C:\\Users\\user\\.dcfs"
                                : "/home/user/.dcfs",
                          }));
                        }
                      }}
                      size="small"
                    >
                      <ToggleButton value="unix">Unix</ToggleButton>
                      <ToggleButton value="windows">Windows</ToggleButton>
                    </ToggleButtonGroup>
                  </Box>
                </Box>
                <div
                  className="bg-slate-700 rounded-lg p-4"
                  style={{ marginBottom: "24px" }}
                >
                  <code className="text-sm text-slate-300 block break-all">
                    docker run --pull=always -it -p {dockerConfig.dcfsPort}:1900 -v{" "}
                    {pathStyle === "windows"
                      ? `"${dockerConfig.dcfsDataDir}:/home/dcfs/.dcfs"`
                      : `${dockerConfig.dcfsDataDir}:/home/dcfs/.dcfs`}{" "}
                    ghcr.io/vulcanosoftware/dcfs:latest
                  </code>
                </div>
                <Typography className="text-slate-300" sx={{ marginBottom: 3 }}>
                  Put your <code>config.yaml</code> in the mounted directory:{" "}
                  <code>
                    {pathStyle === "windows"
                      ? `${dockerConfig.dcfsDataDir}\\config.yaml`
                      : `${dockerConfig.dcfsDataDir}/config.yaml`}
                  </code>
                </Typography>

                <div style={{ marginTop: "24px" }}>
                  <Button
                    variant="contained"
                    onClick={() => setActiveStep(4)}
                    sx={{ mr: 1 }}
                  >
                    Continue
                  </Button>
                </div>
              </StepContent>
            </Step>

            <Step>
              <StepLabel
                onClick={() => setActiveStep(4)}
                sx={{ cursor: "pointer" }}
              >
                <Typography variant="h6" className="text-white">
                  Start Using dcfs
                </Typography>
              </StepLabel>
              <StepContent>
                <Typography className="text-slate-300" sx={{ marginBottom: 3 }}>
                  Once everything is set up, you can access your files through
                  these tested WebDAV clients:
                </Typography>
                <ul
                  className="list-disc list-inside text-slate-300"
                  style={{ marginBottom: "32px" }}
                >
                  <li style={{ marginBottom: "12px" }}>
                    <a
                      href="https://rclone.org/"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      rclone
                    </a>
                  </li>
                  <li style={{ marginBottom: "12px" }}>
                    <a
                      href="https://cyberduck.io/"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      CyberDuck
                    </a>
                  </li>
                  <li style={{ marginBottom: "12px" }}>
                    <a
                      href="https://winscp.net/"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      WinSCP
                    </a>
                  </li>
                  <li style={{ marginBottom: "12px" }}>
                    <a
                      href="https://readdle.com/documents"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Documents
                    </a>
                    &nbsp;by Readdle
                  </li>
                </ul>
                <Typography className="text-slate-300" sx={{ marginBottom: 3 }}>
                  You can also access your files through the WebDAV app:
                </Typography>
                <div style={{ marginBottom: "24px" }}>
                  <Link
                    href="/webdav-app"
                    className="inline-flex items-center px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors"
                  >
                    Open WebDAV App
                  </Link>
                </div>
              </StepContent>
            </Step>
          </Stepper>
        </div>
      </div>
    </div>
  );
}
