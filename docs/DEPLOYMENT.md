# Deployment

Guide for deploying the spectra documentation site.

## Vercel Deployment

### One-Click Deploy

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/adriandarian/spectra&root-directory=docs)

### Manual Setup

1. **Connect your repository** to Vercel at [vercel.com/new](https://vercel.com/new)

2. **Configure the project:**
   - **Framework Preset:** VitePress
   - **Root Directory:** `docs`
   - **Build Command:** `npm run build`
   - **Output Directory:** `.vitepress/dist`

3. **Deploy** - Vercel will automatically deploy on push to main

### Environment Variables

For custom domains, no additional environment variables are needed.

For GitHub Pages (subdirectory deployment):
```
VITEPRESS_BASE=/spectra/
```

## GitHub Pages Deployment

To deploy to GitHub Pages instead:

1. Set the environment variable:
   ```bash
   VITEPRESS_BASE=/spectra/
   ```

2. Build:
   ```bash
   cd docs
   npm run build
   ```

3. Deploy the `.vitepress/dist` folder to GitHub Pages

### GitHub Actions

```yaml
# .github/workflows/docs.yml
name: Deploy Documentation

on:
  push:
    branches: [main]
    paths:
      - 'docs/**'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: docs/package-lock.json

      - name: Install dependencies
        run: cd docs && npm ci

      - name: Build
        run: cd docs && npm run build
        env:
          VITEPRESS_BASE: /spectra/

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: docs/.vitepress/dist
```

## Local Development

```bash
cd docs
npm install
npm run dev
```

Visit http://localhost:5173 to preview.

## Build Locally

```bash
cd docs
npm run build
npm run preview  # Preview the built site
```
