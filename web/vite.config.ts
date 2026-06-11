import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [sveltekit()],
	test: {
		// Explicit include: vitest's default globs silently de-discover tests
		// when files move; pinning the patterns makes zero-discovery loud.
		include: ['src/**/__tests__/**/*.test.ts', 'src/**/*.{test,spec}.ts']
	}
});
