import { Box, Typography, Switch, FormControlLabel } from "@mui/material";
import { ConfigTextField } from "./ConfigTextField";
import { FieldRow } from "./FieldRow";

interface ProtocolConfig {
  enabled: boolean;
  host: string;
  port: number;
}

interface ProtocolSectionProps {
  title: string;
  config: ProtocolConfig;
  onUpdate: (field: keyof ProtocolConfig, value: any) => void;
  defaultPort: number;
}

export const ProtocolSection = ({ title, config, onUpdate, defaultPort }: ProtocolSectionProps) => {
  return (
    <Box sx={{ mt: 3, p: 2, border: 1, borderColor: "divider", borderRadius: 1 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="h6">{title}</Typography>
        <FormControlLabel
          control={
            <Switch
              checked={config.enabled}
              onChange={(e) => onUpdate("enabled", e.target.checked)}
            />
          }
          label="Enabled"
        />
      </Box>

      {config.enabled && (
        <FieldRow>
          <ConfigTextField
            label="Host"
            value={config.host}
            onChange={(e) => onUpdate("host", e.target.value)}
            style={{ flex: 1 }}
          />
          <ConfigTextField
            label="Port"
            type="number"
            value={config.port}
            onChange={(e) => onUpdate("port", parseInt(e.target.value) || defaultPort)}
            width={120}
          />
        </FieldRow>
      )}
    </Box>
  );
};
