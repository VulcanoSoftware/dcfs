"use client";

import { Add, ContentCopy, Delete, Download, Refresh } from "@mui/icons-material";
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
import { ConfigTextField } from "./components/ConfigTextField";
import {
  EncryptionConfig,
  EncryptionField,
} from "./components/EncryptionField";
import { FieldRow } from "./components/FieldRow";
import { FormSection } from "./components/FormSection";
import { UserField } from "./components/UserField";

interface ChannelConfig {
  id: string;
  name: string;
  type: "pinned_message" | "github_repo";
  github_repo?: {
    repo: string;
    commit: string;
    access_token: string;
  };
}

interface ConfigData {
  discord: {
    bot_token: string;
    guild_id: string;
    channels: ChannelConfig[];
  };
  dcfs: {
    users: {
      username: string;
      password: string;
    }[];
    download: {
      chunk_size_kb: number;
    };
    jwt: {
      secret: string;
      algorithm: string;
      life: number;
    };
    server: {
      host: string;
      port: number;
    };
    encryption: EncryptionConfig;
  };
}

// Type-safe path mapping for updateConfig
type ConfigUpdatePaths = {
  "discord.bot_token": string;
  "discord.guild_id": string;
  "discord.channels": ChannelConfig[];
  "dcfs.users": { username: string; password: string }[];
  "dcfs.download.chunk_size_kb": number;
  "dcfs.jwt.secret": string;
  "dcfs.jwt.algorithm": string;
  "dcfs.jwt.life": number;
  "dcfs.server.host": string;
  "dcfs.server.port": number;
  "dcfs.encryption": EncryptionConfig;
};

const generateRandomSecret = (): string => {
  const chars =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()_+-=[]{}|;:,.<>?";
  let result = "";
  for (let i = 0; i < 64; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
};

export default function ConfigGenerator() {
  const [config, setConfig] = useState<ConfigData>({
    discord: {
      bot_token: "",
      guild_id: "",
      channels: [
        {
          id: "",
          name: "default",
          type: "pinned_message",
          github_repo: {
            repo: "",
            commit: "master",
            access_token: "",
          },
        },
      ],
    },
    dcfs: {
      users: [
        {
          username: "user",
          password: "password",
        },
      ],
      download: {
        chunk_size_kb: 1024,
      },
      jwt: {
        secret: "",
        algorithm: "HS256",
        life: 604800,
      },
      server: {
        host: "0.0.0.0",
        port: 1900,
      },
      encryption: {
        enabled: false,
        encrypt_names: false,
        passphrase_source: "passphrase_env",
        passphrase: "",
        passphrase_env: "DCFS_MASTER_PASSPHRASE",
        passphrase_file: "secrets/master.passphrase",
        master_salt_file: "master.salt",
        chunk_size: 65536,
      },
    },
  });

  const updateConfig = useCallback(
    <K extends keyof ConfigUpdatePaths>(
      path: K,
      value: ConfigUpdatePaths[K]
    ): void => {
      const newConfig = { ...config };

      if (path === "discord.bot_token") {
        newConfig.discord.bot_token = value as string;
      } else if (path === "discord.guild_id") {
        newConfig.discord.guild_id = value as string;
      } else if (path === "discord.channels") {
        newConfig.discord.channels = value as ChannelConfig[];
      } else if (path === "dcfs.users") {
        newConfig.dcfs.users = value as {
          username: string;
          password: string;
        }[];
      } else if (path === "dcfs.download.chunk_size_kb") {
        newConfig.dcfs.download.chunk_size_kb = value as number;
      } else if (path === "dcfs.jwt.secret") {
        newConfig.dcfs.jwt.secret = value as string;
      } else if (path === "dcfs.jwt.algorithm") {
        newConfig.dcfs.jwt.algorithm = value as string;
      } else if (path === "dcfs.jwt.life") {
        newConfig.dcfs.jwt.life = value as number;
      } else if (path === "dcfs.server.host") {
        newConfig.dcfs.server.host = value as string;
      } else if (path === "dcfs.server.port") {
        newConfig.dcfs.server.port = value as number;
      } else if (path === "dcfs.encryption") {
        newConfig.dcfs.encryption = value as EncryptionConfig;
      }

      setConfig(newConfig);
    },
    [config]
  );

  // Generate JWT secret on client side only to avoid hydration mismatch
  useEffect(() => {
    if (config.dcfs.jwt.secret === "") {
      updateConfig("dcfs.jwt.secret", generateRandomSecret());
    }
  }, [config.dcfs.jwt.secret, updateConfig]);

  const generateYaml = () => {
    // Build metadata object from channels
    const metadata: {
      [channelId: string]: {
        name: string;
        type: "pinned_message" | "github_repo";
        github_repo?: {
          repo: string;
          commit: string;
          access_token: string;
        };
      };
    } = {};
    config.discord.channels
      .filter((channel) => channel.id.trim() !== "")
      .forEach((channel) => {
        metadata[channel.id] = {
          name: channel.name,
          type: channel.type,
          ...(channel.type === "github_repo" && channel.github_repo
            ? { github_repo: channel.github_repo }
            : {}),
        };
      });

    const configForYaml = {
      discord: {
        bot_token: config.discord.bot_token,
        guild_id: config.discord.guild_id ? parseInt(config.discord.guild_id) : undefined,
        private_file_channel: config.discord.channels
          .filter((channel) => channel.id.trim() !== "")
          .map((channel) => channel.id),
        delete_messages_on_remove: false,
      },
      dcfs: {
        users: config.dcfs.users.reduce((acc, user) => {
          if (user.username.trim() !== "") {
            acc[user.username] = { password: user.password };
          }
          return acc;
        }, {} as { [key: string]: { password: string } }),
        download: config.dcfs.download,
        jwt: config.dcfs.jwt,
        metadata,
        server: config.dcfs.server,
        encryption: (() => {
          const enc = config.dcfs.encryption;
          const block: {
            enabled: boolean;
            encrypt_names: boolean;
            passphrase?: string;
            passphrase_env?: string;
            passphrase_file?: string;
            master_salt_file: string;
            chunk_size: number;
          } = {
            enabled: enc.enabled,
            encrypt_names: enc.encrypt_names,
            master_salt_file: enc.master_salt_file,
            chunk_size: enc.chunk_size,
          };
          if (enc.enabled) {
            if (enc.passphrase_source === "passphrase") {
              block.passphrase = enc.passphrase;
            } else if (enc.passphrase_source === "passphrase_env") {
              block.passphrase_env = enc.passphrase_env;
            } else if (enc.passphrase_source === "passphrase_file") {
              block.passphrase_file = enc.passphrase_file;
            }
          }
          return block;
        })(),
      },
    };

    return yaml.dump(configForYaml, { indent: 2 });
  };

  const downloadConfig = () => {
    const yamlContent = generateYaml();
    const blob = new Blob([yamlContent], { type: "text/yaml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "config.yaml";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const copyToClipboard = () => {
    const yamlContent = generateYaml();
    navigator.clipboard.writeText(yamlContent);
  };

  const regenerateJwtSecret = () => {
    updateConfig("dcfs.jwt.secret", generateRandomSecret());
  };

  const addUser = () => {
    const newUsers = [...config.dcfs.users, { username: "", password: "" }];
    updateConfig("dcfs.users", newUsers);
  };

  const removeUser = (index: number) => {
    const newUsers = config.dcfs.users.filter((_, i) => i !== index);
    updateConfig("dcfs.users", newUsers);
  };

  const updateUser = (
    index: number,
    field: "username" | "password",
    value: string
  ) => {
    const newUsers = [...config.dcfs.users];
    newUsers[index][field] = value;
    updateConfig("dcfs.users", newUsers);
  };

  const addChannel = () => {
    const newChannels = [
      ...config.discord.channels,
      {
        id: "",
        name: `channel-${config.discord.channels.length + 1}`,
        type: "pinned_message" as const,
        github_repo: {
          repo: "",
          commit: "master",
          access_token: "",
        },
      },
    ];
    updateConfig("discord.channels", newChannels);
  };



  const updateChannel = (
    index: number,
    field: "id" | "name",
    value: string
  ) => {
    const newChannels = [...config.discord.channels];
    if (field === "id" || field === "name") {
      newChannels[index][field] = value;
    }
    updateConfig("discord.channels", newChannels);
  };

  const updateChannelType = (
    index: number,
    type: "pinned_message" | "github_repo"
  ) => {
    const newChannels = [...config.discord.channels];
    newChannels[index].type = type;
    if (type === "github_repo" && !newChannels[index].github_repo) {
      newChannels[index].github_repo = {
        repo: "",
        commit: "master",
        access_token: "",
      };
    }
    updateConfig("discord.channels", newChannels);
  };

  const updateChannelGitHubRepo = (
    channelIndex: number,
    field: keyof NonNullable<ChannelConfig["github_repo"]>,
    value: string
  ) => {
    const newChannels = [...config.discord.channels];
    if (!newChannels[channelIndex].github_repo) {
      newChannels[channelIndex].github_repo = {
        repo: "",
        commit: "master",
        access_token: "",
      };
    }
    newChannels[channelIndex].github_repo![field] = value;
    updateConfig("discord.channels", newChannels);
  };

  // Validation functions
  const isValidDirectoryName = (name: string): boolean => {
    const invalidChars = /[\/\\:*?"<>|]/;
    return (
      !invalidChars.test(name) &&
      name !== "." &&
      name !== ".." &&
      name.trim().length > 0
    );
  };

  const getChannelNameErrors = (index: number, name: string): string[] => {
    const errors: string[] = [];

    if (!name.trim()) {
      errors.push("Display name is required");
    } else {
      if (!isValidDirectoryName(name)) {
        errors.push('Invalid characters. Cannot contain: / \\ : * ? " < > |');
      }

      // Check for duplicates
      const duplicateIndex = config.discord.channels.findIndex(
        (channel, i) =>
          i !== index &&
          channel.name.trim().toLowerCase() === name.trim().toLowerCase()
      );
      if (duplicateIndex !== -1) {
        errors.push("Display name must be unique across channels");
      }
    }

    return errors;
  };

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h3" component="h1" gutterBottom align="center">
        dcfs Config Generator
      </Typography>

      <Typography
        variant="h6"
        color="text.secondary"
        align="center"
        sx={{ mb: 4 }}
      >
        Generate your dcfs configuration file with this interactive form
      </Typography>

      <Alert severity="warning" sx={{ mb: 3 }}>
        <AlertTitle>Important</AlertTitle>
        Keep your bot token and channel IDs secure. Never share them publicly.
      </Alert>

      <Box
        sx={{
          display: "flex",
          gap: 3,
          flexDirection: { xs: "column", md: "row" },
        }}
      >
        <Box sx={{ flex: 1 }}>
          <Paper sx={{ p: 3 }}>
            <FormSection title="Discord" showDivider={false}>
              <Typography variant="h6" sx={{ mb: 2 }}>
                Bot Credentials
              </Typography>
              <FieldRow justifyContent="space-between">
                <ConfigTextField
                  label="Bot Token"
                  value={config.discord.bot_token}
                  onChange={(e) =>
                    updateConfig("discord.bot_token", e.target.value)
                  }
                  style={{ flex: 1 }}
                  required
                  type="password"
                />
                <ConfigTextField
                  label="Guild (Server) ID"
                  value={config.discord.guild_id}
                  onChange={(e) =>
                    updateConfig("discord.guild_id", e.target.value)
                  }
                  style={{ flex: 1 }}
                  required
                  helperText="Right-click server → Copy ID"
                />
              </FieldRow>

              <Box sx={{ mt: 3 }}>
                <Typography variant="h6" sx={{ mb: 2 }}>
                  Private File Channels & Metadata
                </Typography>
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ mb: 2 }}
                >
                  Configure one or more private channels to store files. Each
                  channel needs a channel ID and metadata configuration to
                  maintain the directory structure. Right-click a channel → Copy ID.
                </Typography>
                {config.discord.channels.map((channel, index) => (
                  <Box key={index} sx={{ mb: 3, p: 2, border: 1, borderColor: "divider", borderRadius: 1 }}>
                    <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1, mb: 2 }}>
                      <ConfigTextField
                        label="Channel ID"
                        value={channel.id}
                        onChange={(e) => updateChannel(index, "id", e.target.value)}
                        required
                        style={{ flex: 1 }}
                      />
                      <ConfigTextField
                        label="Display Name"
                        value={channel.name}
                        onChange={(e) => updateChannel(index, "name", e.target.value)}
                        required
                        error={getChannelNameErrors(index, channel.name).length > 0}
                        helperText={
                          getChannelNameErrors(index, channel.name).length > 0
                            ? getChannelNameErrors(index, channel.name).join("; ")
                            : "Valid directory name for metadata"
                        }
                        style={{ flex: 1 }}
                      />
                    </Box>

                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      Metadata Type:{" "}
                      <select
                        value={channel.type}
                        onChange={(e) =>
                          updateChannelType(
                            index,
                            e.target.value as "pinned_message" | "github_repo"
                          )
                        }
                        style={{
                          padding: "4px 8px",
                          borderRadius: 4,
                          border: "1px solid #ccc",
                          fontSize: "0.875rem",
                        }}
                      >
                        <option value="pinned_message">Pinned Message</option>
                        <option value="github_repo">GitHub Repository</option>
                      </select>
                    </Typography>

                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      {channel.type === "pinned_message"
                        ? "The metadata will be maintained in a JSON file pinned in the file channel. Every directory operation reuploads and updates the pinned file."
                        : "The metadata will be maintained by a GitHub repository. Every directory operation is mapped to the github repository."}
                    </Typography>

                    {channel.type === "github_repo" && (
                      <>
                        <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
                          <ConfigTextField
                            label="Repository"
                            value={channel.github_repo?.repo || ""}
                            onChange={(e) => updateChannelGitHubRepo(index, "repo", e.target.value)}
                            helperText="Format: username/repository-name"
                            required
                            style={{ flex: 1 }}
                          />
                          <ConfigTextField
                            label="Commit/Branch"
                            value={channel.github_repo?.commit || "master"}
                            onChange={(e) => updateChannelGitHubRepo(index, "commit", e.target.value)}
                            width={200}
                          />
                        </Box>
                        <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
                          <ConfigTextField
                            label="Access Token"
                            value={channel.github_repo?.access_token || ""}
                            onChange={(e) =>
                              updateChannelGitHubRepo(index, "access_token", e.target.value)
                            }
                            type="password"
                            required
                            style={{ flex: 1 }}
                          />
                        </Box>
                      </>
                    )}
                  </Box>
                ))}
                <Box sx={{ display: "flex", gap: 1, mt: 1 }}>
                  {config.discord.channels.length > 1 && (
                    <Button
                      startIcon={<Delete />}
                      color="error"
                      variant="outlined"
                      size="small"
                      onClick={() => {
                        const newChannels = config.discord.channels.slice(0, -1);
                        updateConfig("discord.channels", newChannels);
                      }}
                    >
                      Remove Last Channel
                    </Button>
                  )}
                  <Button
                    startIcon={<Add />}
                    onClick={addChannel}
                    variant="outlined"
                    size="small"
                  >
                    Add Another Channel
                  </Button>
                </Box>
              </Box>
            </FormSection>

            <FormSection title="dcfs">
              <Box>
                <Typography variant="h6" sx={{ mb: 2 }}>
                  Users
                </Typography>
                {config.dcfs.users.map((user, index) => (
                  <UserField
                    key={index}
                    username={user.username}
                    password={user.password}
                    onUsernameChange={(username) =>
                      updateUser(index, "username", username)
                    }
                    onPasswordChange={(password) =>
                      updateUser(index, "password", password)
                    }
                    onDelete={index > 0 ? () => removeUser(index) : undefined}
                    canDelete={index > 0}
                  />
                ))}
                <Button
                  startIcon={<Add />}
                  onClick={addUser}
                  variant="outlined"
                  size="small"
                  sx={{ mt: 1, width: "fit-content" }}
                >
                  Add Another User
                </Button>
              </Box>
              <Typography variant="h6" sx={{ mt: 2, mb: 1 }}>
                JWT
              </Typography>
              <Box sx={{ display: "flex", gap: 1, mb: 2 }}>
                <ConfigTextField
                  label="JWT Secret"
                  value={config.dcfs.jwt.secret}
                  onChange={(e) =>
                    updateConfig("dcfs.jwt.secret", e.target.value)
                  }
                  sx={{ flex: 1 }}
                />
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<Refresh />}
                  onClick={regenerateJwtSecret}
                  sx={{ minWidth: "120px" }}
                >
                  Regenerate
                </Button>
              </Box>
              <Typography variant="h6" sx={{ mt: 2, mb: 1 }}>
                Server
              </Typography>
              <FieldRow>
                <ConfigTextField
                  label="Host"
                  value={config.dcfs.server.host}
                  onChange={(e) =>
                    updateConfig("dcfs.server.host", e.target.value)
                  }
                  width={200}
                />
                <ConfigTextField
                  label="Port"
                  type="number"
                  value={config.dcfs.server.port}
                  onChange={(e) =>
                    updateConfig("dcfs.server.port", parseInt(e.target.value))
                  }
                  width={120}
                />
              </FieldRow>
              <Typography variant="body2" color="text.secondary">
                WebDAV server will be at{" "}
                <code>
                  http://{config.dcfs.server.host}:{config.dcfs.server.port}
                  /webdav
                </code>
              </Typography>
              <Typography variant="body2" color="text.secondary">
                dcfs server will be at{" "}
                <code>
                  http://{config.dcfs.server.host}:{config.dcfs.server.port}
                </code>
              </Typography>
            </FormSection>

            <FormSection title="Encryption (Optional)">
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                At-rest encryption with AES-256-GCM. When enabled, every file
                is encrypted client-side before being uploaded; the Discord
                channel only ever sees ciphertext plus a public per-file salt.
              </Typography>
              <EncryptionField
                config={config.dcfs.encryption}
                onUpdate={(field, value) =>
                  updateConfig("dcfs.encryption", {
                    ...config.dcfs.encryption,
                    [field]: value,
                  })
                }
              />
            </FormSection>
          </Paper>
        </Box>

        <Box sx={{ width: { xs: "100%", md: "400px" }, flexShrink: 0 }}>
          <Paper sx={{ p: 3, position: "sticky", top: 24 }}>
            <Typography variant="h6" gutterBottom>
              Generated Configuration
            </Typography>

            <Box sx={{ mb: 2 }}>
              <Button
                fullWidth
                variant="contained"
                startIcon={<Download />}
                onClick={downloadConfig}
                sx={{ mb: 1 }}
              >
                Download config.yaml
              </Button>
              <Button
                fullWidth
                variant="outlined"
                startIcon={<ContentCopy />}
                onClick={copyToClipboard}
              >
                Copy to Clipboard
              </Button>
            </Box>

            <Card variant="outlined">
              <CardContent sx={{ p: 0 }}>
                <SyntaxHighlighter
                  language="yaml"
                  style={vscDarkPlus}
                  customStyle={{
                    fontSize: "0.75rem",
                    margin: 0,
                  }}
                >
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
