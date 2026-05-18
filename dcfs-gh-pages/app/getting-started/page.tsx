"use client";

import { Apps, ArrowBack, Settings } from "@mui/icons-material";
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
    mountedVolume: "/home/user/.dcfs",
  });

  useEffect(() => {
    if (typeof window !== "undefined") {
      const isWindows = window.navigator.userAgent.includes("Windows");
      setPathStyle(isWindows ? "windows" : "unix");
      setDockerConfig((prev) => ({
        ...prev,
        mountedVolume: isWindows ? "C:\\Users\\user\\.dcfs" : "/home/user/.dcfs",
      }));
    }
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800">
      <div className="container mx-auto px-6 py-12 max-w-4xl">
        <header className="text-center mb-12">
          <Link href="/" className="inline-flex items-center text-slate-400 hover:text-white mb-6 transition-colors">
            <ArrowBack className="w-5 h-5 mr-2" />
            Back to Home
          </Link>
          <h1 className="text-4xl font-bold text-white mb-4">Getting Started with DCFS</h1>
          <p className="text-xl text-slate-300">Follow these steps to set up your Discord File System</p>
        </header>

        <div className="bg-slate-800 rounded-xl p-8 shadow-lg border border-slate-700">
          <Stepper activeStep={activeStep} orientation="vertical">

            {/* Step 1: Create Discord Application */}
            <Step>
              <StepLabel onClick={() => setActiveStep(0)} sx={{ cursor: "pointer" }}>
                <Typography variant="h6" className="text-white">Create a Discord Application &amp; Bot</Typography>
              </StepLabel>
              <StepContent>
                <Typography className="text-slate-300" sx={{ mb: 3 }}>
                  Create a Discord bot that DCFS will use to store files in your channel.
                </Typography>
                <ol className="list-decimal list-inside text-slate-300" style={{ marginBottom: "24px" }}>
                  <li style={{ marginBottom: "12px" }}>
                    Go to{" "}
                    <a href="https://discord.com/developers/applications" target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300 underline">
                      discord.com/developers/applications
                    </a>
                  </li>
                  <li style={{ marginBottom: "12px" }}>Click <strong>New Application</strong>, give it a name</li>
                  <li style={{ marginBottom: "12px" }}>Go to the <strong>Bot</strong> tab → click <strong>Add Bot</strong></li>
                  <li style={{ marginBottom: "12px" }}>
                    Under <strong>Privileged Gateway Intents</strong>, enable:
                    <ul className="list-disc ml-6 mt-1">
                      <li>Message Content Intent</li>
                    </ul>
                  </li>
                  <li style={{ marginBottom: "12px" }}>Click <strong>Reset Token</strong> and copy your bot token — you&apos;ll need it in the config</li>
                </ol>
                <div style={{ marginTop: "24px" }}>
                  <Button variant="contained" onClick={() => setActiveStep(1)} sx={{ mr: 1, bgcolor: "#5865F2", "&:hover": { bgcolor: "#4752C4" } }}>Continue</Button>
                </div>
              </StepContent>
            </Step>

            {/* Step 2: Create a private Discord channel */}
            <Step>
              <StepLabel onClick={() => setActiveStep(1)} sx={{ cursor: "pointer" }}>
                <Typography variant="h6" className="text-white">Create a Private Discord Channel</Typography>
              </StepLabel>
              <StepContent>
                <Typography className="text-slate-300" sx={{ mb: 3 }}>
                  Create a private text channel in your Discord server where DCFS will store your files as message attachments.
                </Typography>
                <ol className="list-decimal list-inside text-slate-300" style={{ marginBottom: "24px" }}>
                  <li style={{ marginBottom: "12px" }}>Open Discord and go to your server (or create a new one)</li>
                  <li style={{ marginBottom: "12px" }}>Create a new <strong>text channel</strong> — name it something like <code className="bg-slate-700 px-2 py-1 rounded">dcfs-storage</code></li>
                  <li style={{ marginBottom: "12px" }}>
                    Invite your bot to the server using the OAuth2 URL Generator in the Developer Portal.
                    Required permissions: <strong>Read Messages, Send Messages, Manage Messages, Attach Files, Read Message History</strong>
                  </li>
                  <li style={{ marginBottom: "12px" }}>
                    Enable <strong>Developer Mode</strong> in Discord settings (Settings → Advanced → Developer Mode),
                    then right-click your storage channel → <strong>Copy Channel ID</strong>
                  </li>
                </ol>
                <div style={{ marginTop: "24px" }}>
                  <Button variant="contained" onClick={() => setActiveStep(2)} sx={{ mr: 1, bgcolor: "#5865F2", "&:hover": { bgcolor: "#4752C4" } }}>Continue</Button>
                </div>
              </StepContent>
            </Step>

            {/* Step 3: Generate Configuration */}
            <Step>
              <StepLabel onClick={() => setActiveStep(2)} sx={{ cursor: "pointer" }}>
                <Typography variant="h6" className="text-white">Generate Configuration</Typography>
              </StepLabel>
              <StepContent>
                <Typography className="text-slate-300" sx={{ mb: 3 }}>
                  Use the config generator to create your DCFS <code className="bg-slate-700 px-2 py-1 rounded">config.yaml</code> file.
                </Typography>
                <div style={{ marginBottom: "24px" }}>
                  <Link href="/config-generator" target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">
                    <Settings className="w-5 h-5 mr-2" />
                    Open Config Generator
                  </Link>
                </div>
                <Typography className="text-slate-400 text-sm" sx={{ mb: 2 }}>
                  Save the generated file to <code className="bg-slate-700 px-2 py-1 rounded">~/.dcfs/config.yaml</code>
                </Typography>
                <div style={{ marginTop: "24px" }}>
                  <Button variant="contained" onClick={() => setActiveStep(3)} sx={{ mr: 1, bgcolor: "#5865F2", "&:hover": { bgcolor: "#4752C4" } }}>Continue</Button>
                </div>
              </StepContent>
            </Step>

            {/* Step 4: Run DCFS */}
            <Step>
              <StepLabel onClick={() => setActiveStep(3)} sx={{ cursor: "pointer" }}>
                <Typography variant="h6" className="text-white">Run DCFS Server</Typography>
              </StepLabel>
              <StepContent>
                <Typography className="text-slate-300" sx={{ mb: 3 }}>
                  Configure and run the DCFS Docker container:
                </Typography>

                <Box sx={{ mb: 3, display: "flex", gap: 2, flexDirection: "column" }}>
                  <Box sx={{ display: "flex", gap: 4 }}>
                    <TextField
                      label="DCFS Port"
                      type="number"
                      value={dockerConfig.dcfsPort}
                      onChange={(e) => setDockerConfig((prev) => ({ ...prev, dcfsPort: parseInt(e.target.value) || 1900 }))}
                      sx={{ "& .MuiInputBase-root": { bgcolor: "#1e293b", color: "white" }, "& .MuiInputLabel-root": { color: "#94a3b8" } }}
                    />
                    <TextField
                      label="Config directory path"
                      value={dockerConfig.mountedVolume}
                      onChange={(e) => setDockerConfig((prev) => ({ ...prev, mountedVolume: e.target.value }))}
                      slotProps={{ input: { endAdornment: <span className="text-slate-400">{pathStyle === "windows" ? "\\config.yaml" : "/config.yaml"}</span> } }}
                      sx={{ flex: 1, "& .MuiInputBase-root": { bgcolor: "#1e293b", color: "white" }, "& .MuiInputLabel-root": { color: "#94a3b8" } }}
                    />
                  </Box>

                  <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
                    <Typography variant="body2" sx={{ color: "#94a3b8" }}>Path Style:</Typography>
                    <ToggleButtonGroup value={pathStyle} exclusive
                      onChange={(_, newStyle) => {
                        if (newStyle) {
                          setPathStyle(newStyle);
                          setDockerConfig((prev) => ({ ...prev, mountedVolume: newStyle === "windows" ? "C:\\Users\\user\\.dcfs" : "/home/user/.dcfs" }));
                        }
                      }} size="small">
                      <ToggleButton value="unix" sx={{ color: "#94a3b8", "&.Mui-selected": { color: "white", bgcolor: "#5865F2" } }}>Unix</ToggleButton>
                      <ToggleButton value="windows" sx={{ color: "#94a3b8", "&.Mui-selected": { color: "white", bgcolor: "#5865F2" } }}>Windows</ToggleButton>
                    </ToggleButtonGroup>
                  </Box>
                </Box>

                <div className="bg-slate-700 rounded-lg p-4" style={{ marginBottom: "24px" }}>
                  <code className="text-sm text-slate-300 block break-all">
                    docker run -it -v {dockerConfig.mountedVolume}:/home/dcfs/.dcfs -p {dockerConfig.dcfsPort}:{dockerConfig.dcfsPort} ghcr.io/YOUR_USERNAME/dcfs
                  </code>
                </div>

                <div style={{ marginTop: "24px" }}>
                  <Button variant="contained" onClick={() => setActiveStep(4)} sx={{ mr: 1, bgcolor: "#5865F2", "&:hover": { bgcolor: "#4752C4" } }}>Continue</Button>
                </div>
              </StepContent>
            </Step>

            {/* Step 5: Start using */}
            <Step>
              <StepLabel onClick={() => setActiveStep(4)} sx={{ cursor: "pointer" }}>
                <Typography variant="h6" className="text-white">Start Using DCFS</Typography>
              </StepLabel>
              <StepContent>
                <Typography className="text-slate-300" sx={{ mb: 3 }}>
                  Once everything is set up, access your files through these WebDAV clients:
                </Typography>
                <ul className="list-disc list-inside text-slate-300" style={{ marginBottom: "32px" }}>
                  {[
                    { name: "rclone", url: "https://rclone.org/" },
                    { name: "CyberDuck", url: "https://cyberduck.io/" },
                    { name: "WinSCP", url: "https://winscp.net/" },
                    { name: "Documents by Readdle", url: "https://readdle.com/documents" },
                    { name: "macOS Finder (Connect to Server → http://localhost:1900)", url: null },
                    { name: "Windows Explorer (Map Network Drive → \\\\localhost@1900\\DavWWWRoot)", url: null },
                  ].map((client) => (
                    <li key={client.name} style={{ marginBottom: "12px" }}>
                      {client.url ? (
                        <a href={client.url} target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300">{client.name}</a>
                      ) : client.name}
                    </li>
                  ))}
                </ul>
                <Typography className="text-slate-300" sx={{ mb: 2 }}>
                  Or use the built-in web file manager:
                </Typography>
                <div style={{ marginBottom: "24px" }}>
                  <Link href="/discord-app"
                    className="inline-flex items-center px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">
                    <Apps className="w-5 h-5 mr-2" />
                    Open File Manager
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
