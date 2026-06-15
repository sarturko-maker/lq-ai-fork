import { describe, expect, it } from 'vitest';
import { sectionHeaderScale } from '../components/primitives/SectionHeader.svelte';

describe('sectionHeaderScale', () => {
	it('renders a page title as an h1 with the large type scale', () => {
		const s = sectionHeaderScale('page');
		expect(s.tag).toBe('h1');
		expect(s.title).toContain('text-2xl');
		expect(s.title).toContain('font-semibold');
		expect(s.subtitle).toContain('text-sm');
	});

	it('renders a section title as an h2 with the compact type scale', () => {
		const s = sectionHeaderScale('section');
		expect(s.tag).toBe('h2');
		expect(s.title).toContain('text-sm');
		expect(s.subtitle).toContain('text-xs');
	});

	it('keeps both titles on the same semantic foreground token', () => {
		expect(sectionHeaderScale('page').title).toContain('text-foreground');
		expect(sectionHeaderScale('section').title).toContain('text-foreground');
		expect(sectionHeaderScale('page').subtitle).toContain('text-muted-foreground');
		expect(sectionHeaderScale('section').subtitle).toContain('text-muted-foreground');
	});
});
