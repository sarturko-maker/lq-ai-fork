/**
 * F2-VL1 (ADR-F013) — pure class helpers for the design-language primitives.
 * Same contract as `pageShellClass`: the primitive's class string is a pure
 * function of its props, so the token-driven idioms (hairline grid, dot-status,
 * rhythm) are locked here without rendering. Variant strings are literal (no
 * interpolation) so Tailwind's JIT keeps them — these tests also guard that.
 */
import { describe, expect, it } from 'vitest';

import { cardClass } from '../components/primitives/Card.svelte';
import { cardGridClass } from '../components/primitives/CardGrid.svelte';
import { inlineClass } from '../components/primitives/Inline.svelte';
import { stackClass } from '../components/primitives/Stack.svelte';
import { statusDotClass } from '../components/primitives/StatusDot.svelte';

describe('stackClass', () => {
	it('is a vertical flex with the default md gap + stretch', () => {
		expect(stackClass()).toBe('flex flex-col gap-4 items-stretch');
	});

	it('maps the 2xl gap to the 64px cockpit section rhythm', () => {
		expect(stackClass('2xl')).toContain('gap-16');
	});

	it('applies alignment and appends trimmed extra', () => {
		expect(stackClass('lg', 'center', '  mt-8 ')).toBe('flex flex-col gap-6 items-center mt-8');
	});
});

describe('inlineClass', () => {
	it('is a centered row with the default sm gap, no wrap', () => {
		expect(inlineClass()).toBe('flex gap-2 items-center justify-start');
	});

	it('adds flex-wrap and maps justify', () => {
		expect(inlineClass('lg', 'center', 'between', true)).toBe(
			'flex flex-wrap gap-5 items-center justify-between'
		);
	});

	it('appends trimmed extra after the base', () => {
		expect(inlineClass('md', 'baseline', 'start', false, ' w-full ')).toBe(
			'flex gap-3 items-baseline justify-start w-full'
		);
	});
});

describe('cardGridClass', () => {
	it('is a hairline grid (1px gap over the border bg, single radius)', () => {
		const cls = cardGridClass();
		expect(cls).toContain('gap-px');
		expect(cls).toContain('bg-border');
		expect(cls).toContain('rounded-lg');
		expect(cls).toContain('overflow-hidden');
	});

	it('collapses columns responsively per column count', () => {
		expect(cardGridClass(1)).toContain('grid-cols-1');
		expect(cardGridClass(2)).toContain('sm:grid-cols-2');
		expect(cardGridClass(3)).toContain('lg:grid-cols-3');
		expect(cardGridClass(4)).toContain('lg:grid-cols-4');
	});
});

describe('cardClass', () => {
	it('is a plain bg-card surface by default (grid supplies the hairline)', () => {
		expect(cardClass()).toBe('bg-card text-card-foreground flex flex-col p-6');
	});

	it('adds its own hairline + 12px radius when bordered (standalone)', () => {
		const cls = cardClass('compact', false, true);
		expect(cls).toContain('p-4');
		expect(cls).toContain('rounded-lg');
		expect(cls).toContain('border');
	});

	it('becomes an interactive control idiom (hover wash + focus ring)', () => {
		const cls = cardClass('default', true);
		expect(cls).toContain('hover:bg-muted');
		expect(cls).toContain('cursor-pointer');
		expect(cls).toContain('focus-visible:ring-2');
	});
});

describe('statusDotClass', () => {
	it('maps running onto the brand-blue status token (VL0 §1)', () => {
		expect(statusDotClass('running')).toBe('bg-status-running');
	});

	it('maps the settled tones onto the status family + faint idle', () => {
		expect(statusDotClass('completed')).toBe('bg-status-completed');
		expect(statusDotClass('failed')).toBe('bg-status-failed');
		expect(statusDotClass('cancelled')).toBe('bg-status-cancelled');
		expect(statusDotClass('idle')).toBe('bg-muted-foreground/40');
	});

	it('maps the attention tone onto --status-attention (VL2 — stale/cap belt)', () => {
		expect(statusDotClass('attention')).toBe('bg-status-attention');
	});
});
