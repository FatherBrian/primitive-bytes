// @ts-check

import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import { defineConfig, fontProviders } from 'astro/config';

// Where the site is served from. On its own domain this becomes ''.
const BASE = '/primitive-bytes';

// https://astro.build/config
export default defineConfig({
	site: 'https://fatherbrian.github.io',
	base: BASE || '/',
	integrations: [mdx(), sitemap()],
	// The Lab used to be called Work.
	redirects: {
		'/work': `${BASE}/lab/`,
		'/work/grant-playground': `${BASE}/lab/grant-playground/`,
		'/work/reef-lock': `${BASE}/lab/reef-lock/`,
	},
	markdown: {
		shikiConfig: {
			// Light by default; global.css switches code blocks to the dark theme.
			themes: { light: 'github-light', dark: 'github-dark-dimmed' },
		},
	},
	fonts: [
		{
			provider: fontProviders.google(),
			name: 'Space Grotesk',
			cssVariable: '--font-display',
			weights: [500, 600, 700],
			fallbacks: ['system-ui', 'sans-serif'],
		},
		{
			provider: fontProviders.google(),
			name: 'Inter',
			cssVariable: '--font-body',
			weights: [400, 500, 600],
			styles: ['normal', 'italic'],
			fallbacks: ['system-ui', 'sans-serif'],
		},
		{
			provider: fontProviders.google(),
			name: 'JetBrains Mono',
			cssVariable: '--font-mono',
			weights: [400, 500],
			fallbacks: ['ui-monospace', 'monospace'],
		},
	],
});
