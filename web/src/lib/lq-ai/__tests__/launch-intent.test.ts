import { describe, expect, it } from 'vitest';
import { launchIntent } from '../cockpit/helpers';

const area = (key: string, configured: boolean) => ({ key, configured });

describe('launchIntent (F2-M4 centered-entry launcher)', () => {
	it('enters the sole configured area and carries the draft', () => {
		const intent = launchIntent([area('commercial', true), area('privacy', false)], 'Review NDA');
		expect(intent.url).toBe('/lq-ai?area=commercial');
		expect(intent.draft).toBe('Review NDA');
	});

	it('does not navigate when several areas are configured (user picks one)', () => {
		const intent = launchIntent([area('commercial', true), area('privacy', true)], 'Review NDA');
		expect(intent.url).toBeNull();
		expect(intent.draft).toBe('Review NDA');
	});

	it('does not navigate when no area is configured', () => {
		const intent = launchIntent([area('commercial', false)], 'Review NDA');
		expect(intent.url).toBeNull();
		expect(intent.draft).toBe('Review NDA');
	});

	it('ignores unconfigured areas when counting the unambiguous destination', () => {
		const intent = launchIntent(
			[area('commercial', true), area('privacy', false), area('disputes', false)],
			'draft'
		);
		expect(intent.url).toBe('/lq-ai?area=commercial');
	});

	it('trims the carried draft', () => {
		expect(launchIntent([area('commercial', true)], '  hello  ').draft).toBe('hello');
	});

	it('handles an empty area list (never navigates)', () => {
		const intent = launchIntent([], 'anything');
		expect(intent.url).toBeNull();
		expect(intent.draft).toBe('anything');
	});
});
