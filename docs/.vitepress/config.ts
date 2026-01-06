import { defineConfig } from 'vitepress'

// Use base path for GitHub Pages, root for Vercel/custom domains
const base = process.env.VITEPRESS_BASE || '/'

export default defineConfig({
  title: 'spectra',
  description: 'Sync markdown documentation to Jira with ease',

  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/logo.svg' }],
    ['meta', { name: 'theme-color', content: '#0052cc' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:title', content: 'spectra - Markdown to Jira Sync' }],
    ['meta', { property: 'og:description', content: 'A production-grade CLI tool for synchronizing markdown documentation with Jira' }],
    ['meta', { property: 'og:url', content: 'https://spectra.dev/' }],
  ],

  base,

  themeConfig: {
    logo: '/logo.svg',

    nav: [
      { text: 'Guide', link: '/guide/getting-started' },
      { text: 'Tutorials', link: '/tutorials/' },
      { text: 'Cookbook', link: '/cookbook/' },
      { text: 'Reference', link: '/reference/cli' },
      {
        text: 'v1.0.0',
        items: [
          { text: 'Changelog', link: '/changelog' },
          { text: 'Contributing', link: '/contributing' },
        ]
      }
    ],

    sidebar: {
      '/guide/': [
        {
          text: 'Introduction',
          items: [
            { text: 'Getting Started', link: '/guide/getting-started' },
            { text: 'Installation', link: '/guide/installation' },
            { text: 'Quick Start', link: '/guide/quick-start' },
          ]
        },
        {
          text: 'Configuration',
          items: [
            { text: 'Config Files', link: '/guide/configuration' },
            { text: 'Environment Variables', link: '/guide/environment' },
            { text: 'Shell Completions', link: '/guide/completions' },
          ]
        },
        {
          text: 'Writing Markdown',
          items: [
            { text: 'Schema Reference', link: '/guide/schema' },
            { text: 'AI Prompts', link: '/guide/ai-prompts' },
            { text: 'AI Fix', link: '/guide/ai-fix' },
          ]
        },
        {
          text: 'Advanced',
          items: [
            { text: 'Architecture', link: '/guide/architecture' },
            { text: 'Plugins', link: '/guide/plugins' },
            { text: 'Adapter Development', link: '/guide/adapter-development' },
            { text: 'Docker', link: '/guide/docker' },
            { text: 'AI Agents', link: '/guide/agents' },
            { text: 'Performance Tuning', link: '/guide/performance' },
          ]
        },
        {
          text: 'Resources',
          items: [
            { text: 'Best Practices', link: '/guide/best-practices' },
            { text: 'Recipes', link: '/guide/recipes' },
            { text: 'Case Studies', link: '/guide/case-studies' },
            { text: 'Troubleshooting', link: '/guide/troubleshooting' },
            { text: 'FAQ', link: '/guide/faq' },
          ]
        }
      ],
      '/reference/': [
        {
          text: 'CLI Reference',
          items: [
            { text: 'Commands', link: '/reference/cli' },
            { text: 'Exit Codes', link: '/reference/exit-codes' },
          ]
        },
        {
          text: 'API Reference',
          items: [
            { text: 'Core Domain', link: '/reference/api/domain' },
            { text: 'Ports & Adapters', link: '/reference/api/ports' },
            { text: 'Hooks System', link: '/reference/api/hooks' },
          ]
        }
      ],
      '/examples/': [
        {
          text: 'Examples',
          items: [
            { text: 'Basic Usage', link: '/examples/basic' },
            { text: 'Epic Template', link: '/examples/template' },
            { text: 'E-commerce Epic', link: '/examples/ecommerce' },
            { text: 'CI/CD Integration', link: '/examples/cicd' },
          ]
        }
      ],
      '/tutorials/': [
        {
          text: 'Video Tutorials',
          items: [
            { text: 'Overview', link: '/tutorials/' },
            { text: 'Your First Sync', link: '/tutorials/first-sync' },
            { text: 'Interactive Mode', link: '/tutorials/interactive-mode' },
            { text: 'Backup & Restore', link: '/tutorials/backup-restore' },
            { text: 'CI/CD Setup', link: '/tutorials/cicd-setup' },
          ]
        }
      ],
      '/cookbook/': [
        {
          text: 'Cookbook',
          items: [
            { text: 'Overview', link: '/cookbook/' },
          ]
        },
        {
          text: 'Workflows',
          items: [
            { text: 'Sprint Planning', link: '/cookbook/sprint-planning' },
            { text: 'Multi-Team', link: '/cookbook/multi-team' },
            { text: 'Release Planning', link: '/cookbook/release-planning' },
          ]
        },
        {
          text: 'Use Cases',
          items: [
            { text: 'Migration Projects', link: '/cookbook/migration' },
            { text: 'Bug Triage', link: '/cookbook/bug-triage' },
            { text: 'Documentation-Driven', link: '/cookbook/documentation-driven' },
          ]
        },
        {
          text: 'Advanced',
          items: [
            { text: 'AI-Assisted Planning', link: '/cookbook/ai-assisted' },
            { text: 'Monorepo Setup', link: '/cookbook/monorepo' },
          ]
        }
      ]
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/adriandarian/spectra' }
    ],

    footer: {
      message: 'Released under the MIT License.',
      copyright: 'Copyright © 2025 Adrian Darian'
    },

    search: {
      provider: 'local'
    },

    editLink: {
      pattern: 'https://github.com/adriandarian/spectra/edit/main/website/:path',
      text: 'Edit this page on GitHub'
    },

    lastUpdated: {
      text: 'Updated at',
      formatOptions: {
        dateStyle: 'medium',
        timeStyle: 'short'
      }
    }
  },

  markdown: {
    theme: {
      light: 'github-light',
      dark: 'one-dark-pro'
    },
    lineNumbers: true
  },

  // Ignore dead links in internal planning docs
  ignoreDeadLinks: [
    /^\/docs\//,
    /plan\//,
  ],

  // Build optimization - split chunks for better caching
  vite: {
    build: {
      chunkSizeWarningLimit: 1000,
      rollupOptions: {
        output: {
          manualChunks(id) {
            // Split shiki (syntax highlighter) - usually the largest
            if (id.includes('shiki') || id.includes('@shikijs')) {
              return 'shiki'
            }
            // Split search related modules
            if (id.includes('minisearch') || id.includes('mark.js')) {
              return 'search'
            }
            // Split vueuse utilities
            if (id.includes('@vueuse')) {
              return 'vueuse'
            }
          }
        }
      }
    }
  },

  lastUpdated: true,
})

