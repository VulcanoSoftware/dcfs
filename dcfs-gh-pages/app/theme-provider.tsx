"use client";

import { ThemeProvider as MuiThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import { discordTheme } from "./webdav-app/discord-theme";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <MuiThemeProvider theme={discordTheme}>
      <CssBaseline />
      {children}
    </MuiThemeProvider>
  );
}
