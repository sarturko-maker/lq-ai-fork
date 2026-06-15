import { describe, expect, it } from 'vitest';
import { TABS, tabGroupOf } from '../tabs';
import { tabStateClass } from '../components/TopTabBar.svelte';

describe('tabGroupOf (F2-M3 presentational grouping)', () => {
	it('defaults to core when no group is set', () => {
		expect(tabGroupOf({ id: 'home', label: 'Home', icon: '', route: '/', available: true })).toBe(
			'core'
		);
	});

	it('classifies the linear executors as legacy and gated surfaces as gated', () => {
		const byId = Object.fromEntries(TABS.map((t) => [t.id, tabGroupOf(t)]));
		expect(byId.playbooks).toBe('legacy');
		expect(byId.tabular).toBe('legacy');
		expect(byId.autonomous).toBe('gated');
		expect(byId.admin).toBe('gated');
	});

	it('leaves everyday surfaces as core', () => {
		for (const id of ['home', 'agents', 'chats', 'matters', 'skills', 'knowledge', 'learn']) {
			expect(tabGroupOf(TABS.find((t) => t.id === id)!)).toBe('core');
		}
	});
});

describe('tabStateClass (F2-M3 tab colour states)', () => {
	it('gives the active tab the single primary accent + underline, regardless of group', () => {
		expect(tabStateClass({ active: true, available: true, legacy: false })).toBe(
			'border-primary text-primary'
		);
		expect(tabStateClass({ active: true, available: true, legacy: true })).toBe(
			'border-primary text-primary'
		);
	});

	it('dims an unavailable (coming-soon) tab the most', () => {
		expect(tabStateClass({ active: false, available: false, legacy: false })).toBe(
			'text-muted-foreground/60'
		);
	});

	it('rests the legacy group one step quieter than core', () => {
		expect(tabStateClass({ active: false, available: true, legacy: true })).toBe(
			'text-muted-foreground/70 hover:text-foreground'
		);
		expect(tabStateClass({ active: false, available: true, legacy: false })).toBe(
			'text-muted-foreground hover:text-foreground'
		);
	});
});
