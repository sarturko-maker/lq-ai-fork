import { describe, expect, it } from 'vitest';
import { TABS, tabGroupOf } from '../tabs';

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
