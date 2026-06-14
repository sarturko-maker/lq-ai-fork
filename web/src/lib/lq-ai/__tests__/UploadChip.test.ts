/**
 * Unit tests for the UploadChip `statusTone` helper (R8).
 *
 * Convention note: this codebase does not install @testing-library/svelte
 * (see AttachedSkillPill.test.ts / AttachKBModal.test.ts). So we follow the
 * established pattern — the .svelte file exports its pure logic from its
 * module script, and we exercise that helper here; the template is glue.
 *
 * These assertions LOCK the WCAG-AA dark-mode lifts into place: each tinted
 * status tone carries an explicit `dark:` foreground (R8 adversarial review
 * fix) so the badge text reads ≥4.5:1 on the charcoal (`bg-card`) surface.
 * A future edit that drops a `dark:` lift fails here instead of silently
 * regressing contrast.
 */
import { describe, expect, it } from 'vitest';
import { statusTone } from '../components/primitives/UploadChip.svelte';

describe('UploadChip statusTone', () => {
	it('maps ready → emerald tone with a dark lift', () => {
		expect(statusTone('ready')).toBe(
			'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
		);
	});

	it('maps processing → amber tone with a dark lift', () => {
		expect(statusTone('processing')).toBe(
			'bg-amber-500/10 text-amber-700 dark:text-amber-300'
		);
	});

	it('maps failed → destructive tone with a dark lift', () => {
		expect(statusTone('failed')).toBe('bg-destructive/10 text-destructive dark:text-red-300');
	});

	it('maps pending → muted tone', () => {
		expect(statusTone('pending')).toBe('bg-muted text-muted-foreground');
	});

	it('falls back to the muted tone for unknown / missing status', () => {
		expect(statusTone(undefined)).toBe('bg-muted text-muted-foreground');
		expect(statusTone('quarantined')).toBe('bg-muted text-muted-foreground');
	});

	it('every tinted tone carries a dark: foreground lift (AA on bg-card)', () => {
		for (const status of ['ready', 'processing', 'failed']) {
			expect(statusTone(status)).toContain('dark:text-');
		}
	});
});
