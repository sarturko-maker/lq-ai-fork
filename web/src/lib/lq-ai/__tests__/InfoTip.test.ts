import { describe, expect, it } from 'vitest';
import { infoTipAccessibleName, infoTipId } from '../components/InfoTip.svelte';

describe('InfoTip helpers', () => {
	describe('infoTipAccessibleName', () => {
		it('falls back to a generic phrase when no label is supplied', () => {
			expect(infoTipAccessibleName(undefined)).toBe('More info');
			expect(infoTipAccessibleName('')).toBe('More info');
			expect(infoTipAccessibleName('   ')).toBe('More info');
		});

		it('embeds a trimmed label so screen readers hear the field name', () => {
			expect(infoTipAccessibleName('Privileged')).toBe('More info about Privileged');
			expect(infoTipAccessibleName('  Skills  ')).toBe('More info about Skills');
		});
	});

	describe('infoTipId', () => {
		it('produces a selector-safe id prefixed with `infotip-`', () => {
			const id = infoTipId('Knowledge Base');
			expect(id).toMatch(/^infotip-KnowledgeBase-\d+$/);
		});

		it('strips non-alphanumeric characters from the seed', () => {
			const id = infoTipId('skill — picker!');
			expect(id).toMatch(/^infotip-skillpicker-\d+$/);
		});

		it('falls back to `x` when the seed is empty after stripping', () => {
			const id = infoTipId('—');
			expect(id).toMatch(/^infotip-x-\d+$/);
		});

		it('caps the seed at 20 characters so ids stay compact', () => {
			const id = infoTipId('a'.repeat(100));
			expect(id).toMatch(/^infotip-a{20}-\d+$/);
		});
	});
});
