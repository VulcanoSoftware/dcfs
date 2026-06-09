"use client";

import { Box, Button, Typography } from "@mui/material";

export default function JoinGroup() {
  return (
    <Box sx={{ textAlign: "center", mt: 6, px: 2 }}>
      <Typography variant="h4" sx={{ mb: 2 }}>
        Support
      </Typography>
      <Typography sx={{ mb: 3 }}>
        For questions, bug reports, and feature requests, use GitHub Discussions
        or open an issue.
      </Typography>
      <Box
        sx={{
          display: "flex",
          justifyContent: "center",
          gap: 2,
          flexWrap: "wrap",
        }}
      >
        <Button
          variant="contained"
          href="https://github.com/VulcanoSoftware/dcfs/discussions"
          target="_blank"
          rel="noopener noreferrer"
        >
          GitHub Discussions
        </Button>
        <Button
          variant="outlined"
          href="https://github.com/VulcanoSoftware/dcfs/issues"
          target="_blank"
          rel="noopener noreferrer"
        >
          GitHub Issues
        </Button>
      </Box>
    </Box>
  );
}
