import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		// Static SPA: every route renders client-side (ssr=false in the root
		// +layout.js); fallback is mandatory so deep links like
		// /lq-ai/tabular/[id] resolve on the static server (F0-S6 contract).
		adapter: adapter({
			pages: 'build',
			assets: 'build',
			fallback: 'index.html'
		})
	},
	onwarn: (warning, handler) => {
		// lq-ai components carry scoped <style> blocks whose selectors target
		// markup rendered conditionally — the unused-selector warning is noise.
		if (warning.code === 'css-unused-selector') return;
		handler(warning);
	}
};

export default config;
