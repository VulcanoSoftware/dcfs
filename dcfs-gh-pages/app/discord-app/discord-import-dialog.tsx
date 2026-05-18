"use client";

import { Attachment, CheckCircle, Storage } from "@mui/icons-material";
import {
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  TextField,
  Typography,
} from "@mui/material";
import mime from "mime-types";
import { useCallback, useEffect, useMemo, useState } from "react";
import ManagerClient, { ChannelMessage } from "./manager-client";

interface DiscordImportDialogProps {
  open: boolean;
  onClose: () => void;
  onImport: (
    channelId: number,
    messageId: number,
    asName: string
  ) => Promise<void>;
  managerClient: ManagerClient;
}

export default function DiscordImportDialog({
  open,
  onClose,
  onImport,
  managerClient,
}: DiscordImportDialogProps) {
  const [discordLink, setDiscordLink] = useState("");
  const [messagePreview, setMessagePreview] = useState<ChannelMessage | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [channelId, setChannelId] = useState<number | null>(null);
  const [messageId, setMessageId] = useState<number | null>(null);
  const [asName, setAsName] = useState<string>("unnamed");

  /**
   * Parse a Discord message link.
   * Formats:
   *   https://discord.com/channels/GUILD_ID/CHANNEL_ID/MESSAGE_ID
   *   https://discord.com/channels/@me/CHANNEL_ID/MESSAGE_ID
   */
  const extractMessageInfo = useCallback(
    (link: string): { messageId: number; channelId: number } => {
      const url = new URL(link);
      const parts = url.pathname.replace(/^\//, "").split("/");
      // parts: ["channels", guildId|"@me", channelId, messageId]
      if (parts[0] !== "channels" || parts.length < 4) {
        throw new Error("Invalid Discord message link. Expected format: https://discord.com/channels/SERVER_ID/CHANNEL_ID/MESSAGE_ID");
      }
      const channelId = parseInt(parts[2]);
      const messageId = parseInt(parts[3]);
      if (isNaN(channelId) || isNaN(messageId)) {
        throw new Error("Could not parse channel or message ID from the link.");
      }
      return { channelId, messageId };
    },
    []
  );

  useEffect(() => {
    if (!open) {
      setMessagePreview(null);
      setPreviewLoading(false);
      setErrorMessage(null);
    }
  }, [open]);

  useEffect(() => {
    if (!discordLink.trim()) {
      setMessagePreview(null);
      setPreviewLoading(false);
      setErrorMessage(null);
      return;
    }

    setPreviewLoading(true);
    setMessagePreview(null);

    const debounceTimer = setTimeout(async () => {
      if (!discordLink.trim()) return;
      try {
        const { channelId, messageId } = extractMessageInfo(discordLink);
        const messageInfo = await managerClient.getMessage(channelId, messageId);
        setChannelId(channelId);
        setMessageId(messageId);
        setMessagePreview(messageInfo);
        setErrorMessage(null);
      } catch (error) {
        setMessagePreview(null);
        setErrorMessage(error instanceof Error ? error.message : "Unknown error");
      } finally {
        setPreviewLoading(false);
      }
    }, 1000);

    return () => clearTimeout(debounceTimer);
  }, [discordLink, managerClient, extractMessageInfo]);

  const resetDialog = useCallback(() => {
    setDiscordLink("");
    setMessagePreview(null);
    setPreviewLoading(false);
    setChannelId(null);
    setMessageId(null);
    setAsName("unnamed");
    onClose();
  }, [onClose]);

  const handleImport = useCallback(async () => {
    if (channelId && messageId && asName.trim().length > 0) {
      try {
        await onImport(channelId, messageId, asName);
        resetDialog();
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : "Unknown error");
      }
    }
  }, [channelId, messageId, asName, onImport, resetDialog]);

  const sanitizeFileName = useCallback((name: string | null | undefined): string => {
    return (
      name
        ?.replace(/[^a-zA-Z0-9_\u00A0-\uFFFF]/g, "_")
        .replace(/_{2,}/g, "_")
        .trim() ?? "unnamed"
    );
  }, []);

  useEffect(() => {
    if (messagePreview) {
      const fileType = mime.extension(messagePreview.mime_type) || "bin";
      setAsName((sanitizeFileName(messagePreview.caption) || "unnamed") + `.${fileType}`);
    }
  }, [messagePreview, sanitizeFileName]);

  const errorBlock = useMemo(
    () =>
      errorMessage && (
        <Paper elevation={2} sx={{ mt: 3, p: 3, borderRadius: 2, border: 1, borderColor: "error.main", bgcolor: "rgba(237,66,69,0.08)" }}>
          <Typography variant="h6" sx={{ color: "error.main", fontWeight: 600 }}>
            {errorMessage}
          </Typography>
        </Paper>
      ),
    [errorMessage]
  );

  const previewBlock = useMemo(() => {
    if (!messagePreview || errorMessage) return null;
    return (
      <Paper elevation={2} sx={{ mt: 3, p: 3, borderRadius: 2, border: 1, borderColor: "success.main", bgcolor: "rgba(87,242,135,0.08)" }}>
        <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
          <CheckCircle sx={{ color: "success.main", mr: 1 }} />
          <Typography variant="h6" sx={{ color: "success.main", fontWeight: 600 }}>
            File Ready for Import
          </Typography>
        </Box>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
          <Box sx={{ display: "flex", alignItems: "center" }}>
            <Storage sx={{ color: "text.secondary", mr: 1, fontSize: 18 }} />
            <Typography variant="body2" color="text.secondary" sx={{ mr: 1 }}>Size:</Typography>
            <Typography variant="body2" sx={{ fontWeight: 500 }}>
              {managerClient?.formatFileSize(messagePreview.file_size)}
            </Typography>
          </Box>
          <Box sx={{ display: "flex", alignItems: "center" }}>
            <Attachment sx={{ color: "text.secondary", mr: 1, fontSize: 18 }} />
            <Typography variant="body2" color="text.secondary" sx={{ mr: 1 }}>Type:</Typography>
            <Typography variant="body2" sx={{ fontWeight: 500 }}>{messagePreview.mime_type}</Typography>
          </Box>
          {messagePreview.caption && (
            <Box sx={{ mt: 1 }}>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5, fontWeight: 500 }}>Caption:</Typography>
              <Typography variant="body2" sx={{ bgcolor: "background.default", p: 1.5, borderRadius: 1, border: 1, borderColor: "divider", fontStyle: "italic", wordBreak: "break-word" }}>
                {messagePreview.caption}
              </Typography>
            </Box>
          )}
        </Box>
      </Paper>
    );
  }, [messagePreview, managerClient, errorMessage]);

  return (
    <Dialog open={open} onClose={resetDialog} PaperProps={{ sx: { bgcolor: "background.paper", minWidth: 480 } }}>
      <DialogTitle>Import Discord File</DialogTitle>
      <DialogContent>
        <TextField
          autoFocus
          label="Discord Message Link"
          value={discordLink}
          onChange={(e) => setDiscordLink(e.target.value)}
          fullWidth
          margin="normal"
          placeholder="https://discord.com/channels/123.../456.../789..."
          helperText="Right-click a Discord message → Copy Message Link"
          InputProps={{
            endAdornment: previewLoading && <CircularProgress size={20} sx={{ color: "text.secondary" }} />,
          }}
        />
        <TextField
          label="File Name"
          value={asName}
          onChange={(e) => setAsName(e.target.value)}
          fullWidth
          margin="normal"
          placeholder="unnamed"
        />
        {errorBlock}
        {previewBlock}
      </DialogContent>
      <DialogActions>
        <Button onClick={resetDialog}>Cancel</Button>
        <Button
          onClick={handleImport}
          disabled={!messagePreview || !!errorMessage}
          variant="contained"
        >
          Import File
        </Button>
      </DialogActions>
    </Dialog>
  );
}
