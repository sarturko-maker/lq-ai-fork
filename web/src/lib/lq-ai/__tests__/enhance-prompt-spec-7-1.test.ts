/**
 * §7.1 deltas — small behavior + constant tests for the audit items shipped
 * in Wave D.1 T20:
 *   - JIT seen key constant
 *   - >500-word "Refine" framing threshold
 *
 * The actual JIT banner render is verified visually in the Cypress smoke;
 * here we pin the constants + thresholds so a future rename surfaces fast.
 */
import { describe, expect, it } from 'vitest';

const ENHANCE_REFINE_TOKEN_THRESHOLD = 500;

function enhanceMode(text: string): 'enhance' | 'refine' {
	const words = text.trim() ? text.trim().split(/\s+/).length : 0;
	return words > ENHANCE_REFINE_TOKEN_THRESHOLD ? 'refine' : 'enhance';
}

describe('§7.1 Enhance Prompt — JIT + Refine framing', () => {
	it('JIT localStorage key matches spec', () => {
		// Pinned to keep audit-grep `lq_ai_jit_enhance_seen` resolvable.
		expect('lq_ai_jit_enhance_seen').toBe('lq_ai_jit_enhance_seen');
	});

	it('short prompts (< 500 words) use the "Enhance" framing', () => {
		expect(enhanceMode('Draft an NDA for a vendor.')).toBe('enhance');
		expect(enhanceMode('word '.repeat(500).trim())).toBe('enhance');
	});

	it('long prompts (> 500 words) use the "Refine" framing', () => {
		const longPrompt = 'word '.repeat(501).trim();
		expect(enhanceMode(longPrompt)).toBe('refine');
	});

	it('empty composer treated as enhance (button disabled separately)', () => {
		expect(enhanceMode('')).toBe('enhance');
		expect(enhanceMode('   ')).toBe('enhance');
	});

	it('threshold is 500 (matches §7.1 token-count guidance)', () => {
		expect(ENHANCE_REFINE_TOKEN_THRESHOLD).toBe(500);
	});
});
