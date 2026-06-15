import { describe, expect, it } from 'vitest';
import { pageShellClass } from '../components/primitives/PageShell.svelte';

describe('pageShellClass', () => {
	it('centers + caps width and applies the calm padding default', () => {
		const cls = pageShellClass('default');
		expect(cls).toBe('mx-auto w-full max-w-4xl px-6 py-10 sm:px-8');
	});

	it('maps each size to its reading-width cap', () => {
		expect(pageShellClass('narrow')).toContain('max-w-3xl');
		expect(pageShellClass('default')).toContain('max-w-4xl');
		expect(pageShellClass('wide')).toContain('max-w-5xl');
	});

	it('maps each pad variant to its rhythm (F2-M6)', () => {
		expect(pageShellClass('default', 'default')).toContain('px-6 py-10 sm:px-8');
		expect(pageShellClass('default', 'compact')).toBe('mx-auto w-full max-w-4xl px-6 py-8 sm:px-8');
		expect(pageShellClass('narrow', 'tight')).toBe('mx-auto w-full max-w-3xl px-4 py-4 sm:px-6');
	});

	it('appends trimmed extra classes after the base', () => {
		expect(pageShellClass('default', 'default', '  mt-4  ')).toBe(
			'mx-auto w-full max-w-4xl px-6 py-10 sm:px-8 mt-4'
		);
	});

	it('omits the trailing space when no extra is given', () => {
		expect(pageShellClass('narrow', 'default', '   ')).toBe(
			'mx-auto w-full max-w-3xl px-6 py-10 sm:px-8'
		);
	});
});
