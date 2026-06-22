import { describe, expect, it, vi } from 'vitest';

// `renderModelMarkdown` couples marked (parser) + DOMPurify (sanitiser).
// DOMPurify needs a DOM, and this repo's vitest runs in the `node` env with no
// jsdom — so we stub the sanitiser to a pass-through. This guards the PARSER
// config (the thing a future change could regress): the cockpit-chat-UX slice
// proved GFM tables already parse — marked 9 defaults `gfm:true`, so the
// rumoured "missing gfm flag" bug was a red herring; the real defect was CSS
// (dark-mode `prose`). The media-forbid policy (table tags are NOT on its
// FORBID list, so they survive) is verified by the live screenshot DoD.
vi.mock('dompurify', () => ({ default: { sanitize: (html: string) => html } }));

import { renderModelMarkdown } from '../sanitize-markdown';

describe('renderModelMarkdown — GFM tables', () => {
	it('emits an HTML <table> for a pipe table', () => {
		const html = renderModelMarkdown('| A | B |\n|---|---|\n| 1 | 2 |');
		expect(html).toContain('<table>');
		expect(html).toContain('<th>');
		expect(html).toContain('<td>');
	});

	it('renders strikethrough and task lists (GFM)', () => {
		expect(renderModelMarkdown('~~gone~~')).toContain('<del>');
		expect(renderModelMarkdown('- [x] done')).toContain('type="checkbox"');
	});

	it('returns an empty string for nullish input', () => {
		expect(renderModelMarkdown(undefined)).toBe('');
		expect(renderModelMarkdown(null)).toBe('');
		expect(renderModelMarkdown('')).toBe('');
	});
});
