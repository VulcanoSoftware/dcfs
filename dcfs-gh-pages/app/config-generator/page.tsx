"use client";

import { Add, ContentCopy, Download, Refresh } from "@mui/icons-material";
import {
  Alert,
  AlertTitle,
  Box,
  Button,
  Card,
  CardContent,
  Container,
  Paper,
  Typography,
} from "@mui/material";
import yaml from "js-yaml";
import { useCallback, useEffect, useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { BotTokenField } from "./components/BotTokenField";
import { ChannelField } from "./components/ChannelField";
import { ConfigTextField } from "./components/ConfigTextField";
import { FieldRow } from "./components/FieldRow";
import { FormSection } from "./components/FormSection";
import { UserField } from "./components/UserField";

interface ChannelConfig {
  id: string;
  name: string;
  type: "pinned_message" | "github_repo";
  github_repo?: { repo: string; commit: string; access_token: string };
}

interface ConfigData {
  discord: {
    bot_tokens: string[];
    channels: ChannelConfig[];
    max_file_size_mb: number;
  };
  tgfs: {
    users: { username: string; password: string }[];
    download: { chunk_size_kb: number };
    jwt: { secret: string; algorithm: string; life: number };
    server: { host: string; port: number };
  };
}

type ConfigUpdatePaths = {
  "discord.bot_tokens": string[];
  "discord.channels": ChannelConfig[];
  "discord.max_file_size_mb": number;
  "tgfs.users": { username: string; password: string }[];
  "tgfs.download.chunk_size_kb": number;
  "tgfs.jwt.secret": string;
  "tgfs.jwt.algorithm": string;
  "tgfs.jwt.life": number;
  "tgfs.server.host": string;
  "tgfs.server.port": number;
};

const generateRandomSecret = (): string => {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()_+-=[]{}|;:,.<>?";
  let result = "";
  for (let i = 0; i < 64; i++) result += chars.charAt(Math.floor(Math.random() * chars.length));
  return result;
};

export default function ConfigGenerator() {
  const [config, setConfig] = useState<ConfigData>({
    discord: {
      bot_tokens: [""],
      channels: [{ id: "", name: "default", type: "pinned_message", github_repo: { repo: "", commit: "master", access_token: "" } }],
      max_file_size_mb: 25,
    },
    tgfs: {
      users: [{ username: "user", password: "password" }],
      download: { chunk_size_kb: 1024 },
      jwt: { secret: "", algorithm: "HS256", life: 604800 },
      server: { host: "0.0.0.0", port: 1900 },
    },
  });

  const updateConfig = useCallback(<K extends keyof ConfigUpdatePaths>(path: K, value: ConfigUpdatePaths[K]): void => {
    const newConfig = { ...config };
    if (path === "discord.bot_tokens") newConfig.discord.bot_tokens = value as string[];
    else if (path === "discord.channels") newConfig.discord.channels = value as ChannelConfig[];
    else if (path === "discord.max_file_size_mb") newConfig.discord.max_file_size_mb = value as number;
    else if (path === "tgfs.users") newConfig.tgfs.users = value as { username: string; password: string }[];
    else if (path === "tgfs.download.chunk_size_kb") newConfig.tgfs.download.chunk_size_kb = value as number;
    else if (path === "tgfs.jwt.secret") newConfig.tgfs.jwt.secret = value as string;
    else if (path === "tgfs.jwt.algorithm") newConfig.tgfs.jwt.algorithm = value as string;
    else if (path === "tgfs.jwt.life") newConfig.tgfs.jwt.life = value as number;
    else if (path === "tgfs.server.host") newConfig.tgfs.server.host = value as string;
    else if (path === "tgfs.server.port") newConfig.tgfs.server.port = value as number;
    setConfig(newConfig);
  }, [config]);

  useEffect(() => {
    if (config.tgfs.jwt.secret === "") updateConfig("tgfs.jwt.secret", generateRandomSecret());
  }, [config.tgfs.jwt.secret, updateConfig]);

  const addBotToken = () => updateConfig("discord.bot_tokens", [...config.discord.bot_tokens, ""]);
  const removeBotToken = (index: number) => updateConfig("discord.bot_tokens", config.discord.bot_tokens.filter((_, i) => i !== index));
  const updateBotToken = (index: number, value: string) => {
    const t = [...config.discord.bot_tokens]; t[index] = value; updateConfig("discord.bot_tokens", t);
  };

  const addUser = () => updateConfig("tgfs.users", [...config.tgfs.users, { username: "", password: "" }]);
  const removeUser = (index: number) => updateConfig("tgfs.users", config.tgfs.users.filter((_, i) => i !== index));
  const updateUser = (index: number, field: "username" | "password", value: string) => {
    const u = [...config.tgfs.users]; u[index][field] = value; updateConfig("tgfs.users", u);
  };

  const addChannel = () => updateConfig("discord.channels", [...config.discord.channels, {
    id: "", name: `channel-${config.discord.channels.length + 1}`, type: "pinned_message" as const,
    github_repo: { repo: "", commit: "master", access_token: "" },
  }]);
  const removeChannel = (index: number) => updateConfig("discord.channels", config.discord.channels.filter((_, i) => i !== index));

  const isValidDirectoryName = (name: string): boolean => {
    return !/[\/\\:*?"<>|]/.test(name) && name !== "." && name !== ".." && name.trim().length > 0;
  };

  const getChannelNameErrors = (index: number, name: string): string[] => {
    const errors: string[] = [];
    if (!name.trim()) { errors.push("Display name is required"); return errors; }
    if (!isValidDirectoryName(name)) errors.push('Invalid characters. Cannot contain: / \\ : * ? " < > |');
    const dup = config.discord.channels.findIndex((c, i) => i !== index && c.name.trim().toLowerCase() === name.trim().toLowerCase());
    if (dup !== -1) errors.push("Display name must be unique across channels");
    return errors;
  };

  const updateChannel = (index: number, field: "id" | "name" | "type", value: string) => {
    const c = [...config.discord.channels];
    if (field === "type") c[index][field] = value as "pinned_message" | "github_repo";
    else c[index][field] = value;
    updateConfig("discord.channels", c);
  };

  const updateChannelGitHubRepo = (channelIndex: number, field: keyof NonNullable<ChannelConfig["github_repo"]>, value: string) => {
    const c = [...config.discord.channels];
    if (!c[channelIndex].github_repo) c[channelIndex].github_repo = { repo: "", commit: "master", access_token: "" };
    c[channelIndex].github_repo![field] = value;
    updateConfig("discord.channels", c);
  };

  const generateYaml = () => {
    const metadata: Record<string, { name: string; type: string; github_repo?: object }> = {};
    config.discord.channels.filter((ch) => ch.id.trim() !== "").forEach((ch) => {
      metadata[ch.id] = { name: ch.name, type: ch.type, ...(ch.type === "github_repo" && ch.github_repo ? { github_repo: ch.github_repo } : {}) };
    });

    const configForYaml = {
      discord: {
        bot_tokens: config.discord.bot_tokens.filter((t) => t.trim() !== ""),
        private_file_channel: config.discord.channels.filter((ch) => ch.id.trim() !== "").map((ch) => ch.id),
        max_file_size_mb: config.discord.max_file_size_mb,
      },
      tgfs: {
        users: config.tgfs.users.reduce((acc, u) => {
          if (u.username.trim()) acc[u.username] = { password: u.password };
          return acc;
        }, {} as Record<string, { password: string }>),
        download: config.tgfs.download,
        jwt: config.tgfs.jwt,
        metadata,
        server: config.tgfs.server,
      },
    };
    return yaml.dump(configForYaml, { indent: 2 });
  };

  const downloadConfig = () => {
    const blob = new Blob([generateYaml()], { type: "text/yaml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "config.yaml";
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const copyToClipboard = () => navigator.clipboard.writeText(generateYaml());
  const regenerateJwtSecret = () => updateConfig("tgfs.jwt.secret", generateRandomSecret());

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h3" component="h1" gutterBottom align="center">DCFS Config Generator</Typography>
      <Typography variant="h6" color="text.secondary" align="center" sx={{ mb: 4 }}>
        Generate your DCFS <code>config.yaml</code> interactively
      </Typography>

      <Alert severity="warning" sx={{ mb: 3 }}>
        <AlertTitle>Keep your bot token secure</AlertTitle>
        Never share your Discord bot token publicly. Anyone with the token can control your bot.
      </Alert>

      <Box sx={{ display: "flex", gap: 3, flexDirection: { xs: "column", md: "row" } }}>
        <Box sx={{ flex: 1 }}>
          <Paper sx={{ p: 3 }}>

            {/* Discord section */}
            <FormSection title="Discord" showDivider={false}>
              <Box>
                <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                  <Typography variant="h6">Bot Token(s)</Typography>
                  <Button variant="outlined" size="small" component="a" href="https://discord.com/developers/applications" target="_blank" rel="noopener noreferrer" sx={{ textTransform: "none" }}>
                    Discord Developer Portal
                  </Button>
                </Box>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Multiple tokens distribute upload traffic across bots, just like the original multi-bot setup.
                </Typography>
                {config.discord.bot_tokens.map((token, index) => (
                  <BotTokenField key={index} index={index} value={token}
                    onChange={(value) => updateBotToken(index, value)}
                    onDelete={index > 0 ? () => removeBotToken(index) : undefined} />
                ))}
                <Button startIcon={<Add />} onClick={addBotToken} variant="outlined" size="small" sx={{ mt: 1 }}>
                  Add Another Bot Token
                </Button>
              </Box>

              <Box sx={{ mt: 3 }}>
                <Typography variant="h6" sx={{ mb: 1 }}>Max File Size per Attachment (MB)</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  25 MB for free servers · 50 MB (Level 2 boost) · 100 MB (Level 3) · 500 MB (Nitro sender)
                </Typography>
                <ConfigTextField
                  label="Max file size (MB)"
                  type="number"
                  value={config.discord.max_file_size_mb}
                  onChange={(e) => updateConfig("discord.max_file_size_mb", parseInt(e.target.value) || 25)}
                  width={160}
                />
              </Box>

              <Box sx={{ mt: 3 }}>
                <Typography variant="h6" sx={{ mb: 1 }}>Storage Channels</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Enter the Channel ID of each Discord channel used for file storage. Enable Developer Mode in Discord
                  (Settings → Advanced → Developer Mode), then right-click the channel → Copy Channel ID.
                </Typography>
                {config.discord.channels.map((channel, index) => (
                  <ChannelField key={index} index={index} channel={channel}
                    onUpdate={(field, value) => updateChannel(index, field, value)}
                    onUpdateGitHubRepo={(field, value) => updateChannelGitHubRepo(index, field, value)}
                    onDelete={config.discord.channels.length > 1 ? () => removeChannel(index) : undefined}
                    canDelete={config.discord.channels.length > 1}
                    nameErrors={getChannelNameErrors(index, channel.name)}
                  />
                ))}
                <Button startIcon={<Add />} onClick={addChannel} variant="outlined" size="small" sx={{ mt: 1 }}>
                  Add Another Channel
                </Button>
              </Box>
            </FormSection>

            {/* Server settings section */}
            <FormSection title="Server Settings">
              <Box>
                <Typography variant="h6" sx={{ mb: 2 }}>Users</Typography>
                {config.tgfs.users.map((user, index) => (
                  <UserField key={index} username={user.username} password={user.password}
                    onUsernameChange={(v) => updateUser(index, "username", v)}
                    onPasswordChange={(v) => updateUser(index, "password", v)}
                    onDelete={index > 0 ? () => removeUser(index) : undefined}
                    canDelete={index > 0}
                  />
                ))}
                <Button startIcon={<Add />} onClick={addUser} variant="outlined" size="small" sx={{ mt: 1, width: "fit-content" }}>
                  Add Another User
                </Button>
              </Box>

              <Typography variant="h6" sx={{ mt: 2, mb: 1 }}>JWT</Typography>
              <Box sx={{ display: "flex", gap: 1, mb: 2 }}>
                <ConfigTextField label="JWT Secret" value={config.tgfs.jwt.secret} onChange={(e) => updateConfig("tgfs.jwt.secret", e.target.value)} sx={{ flex: 1 }} />
                <Button variant="outlined" size="small" startIcon={<Refresh />} onClick={regenerateJwtSecret} sx={{ minWidth: "120px" }}>Regenerate</Button>
              </Box>

              <Typography variant="h6" sx={{ mt: 2, mb: 1 }}>Server</Typography>
              <FieldRow>
                <ConfigTextField label="Host" value={config.tgfs.server.host} onChange={(e) => updateConfig("tgfs.server.host", e.target.value)} width={200} />
                <ConfigTextField label="Port" type="number" value={config.tgfs.server.port} onChange={(e) => updateConfig("tgfs.server.port", parseInt(e.target.value))} width={120} />
              </FieldRow>
              <Typography variant="body2" color="text.secondary">
                WebDAV at <code>http://{config.tgfs.server.host}:{config.tgfs.server.port}/webdav</code>
              </Typography>
            </FormSection>
          </Paper>
        </Box>

        {/* Preview panel */}
        <Box sx={{ width: { xs: "100%", md: "400px" }, flexShrink: 0 }}>
          <Paper sx={{ p: 3, position: "sticky", top: 24 }}>
            <Typography variant="h6" gutterBottom>Generated Configuration</Typography>
            <Box sx={{ mb: 2 }}>
              <Button fullWidth variant="contained" startIcon={<Download />} onClick={downloadConfig} sx={{ mb: 1 }}>Download config.yaml</Button>
              <Button fullWidth variant="outlined" startIcon={<ContentCopy />} onClick={copyToClipboard}>Copy to Clipboard</Button>
            </Box>
            <Card variant="outlined">
              <CardContent sx={{ p: 0 }}>
                <SyntaxHighlighter language="yaml" style={vscDarkPlus} customStyle={{ fontSize: "0.75rem", margin: 0 }}>
                  {generateYaml()}
                </SyntaxHighlighter>
              </CardContent>
            </Card>
          </Paper>
        </Box>
      </Box>
    </Container>
  );
}
