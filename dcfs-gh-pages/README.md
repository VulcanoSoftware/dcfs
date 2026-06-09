# dcfs GitHub Pages

This is the web frontend for [dcfs](https://github.com/VulcanoSoftware/dcfs) — Discord becomes a WebDAV server. Built with [Next.js](https://nextjs.org) and [MUI](https://mui.com/).

## Features

- **Config Generator** — Interactive form to generate `config.yaml` with validation for channels, users, JWT, encryption
- **Getting Started Guide** — Step-by-step wizard for setting up Discord bot, channels, and dcfs server
- **WebDAV App** — Built-in file explorer with upload, download, delete, directory creation, Discord message import, and background task tracking (when the manager API is available)

## Development

```bash
npm install
npm run dev        # Start development server with Turbopack
npm run build      # Production build (static export for GitHub Pages)
```

The site is deployed to GitHub Pages on every push to `main`.

## Structure

```
app/
  config-generator/   # Config YAML generator page
  getting-started/    # Step-by-step setup guide
  join-group/         # Support links
  webdav-app/         # Built-in WebDAV file explorer
  layout.tsx          # Root layout with MUI ThemeProvider
  page.tsx            # Landing page
```
