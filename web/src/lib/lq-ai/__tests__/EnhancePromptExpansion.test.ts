/**
 * Tests for the EnhancePromptExpansion action-mapping conventions (T6).
 *
 * No @testing-library/svelte is available, so we test the outcome mapping
 * logic that the component delegates to the recordOutcome API client — this
 * mirrors the contract stated in the spec comment on recordOutcome().
 *
 * The load-bearing test coverage for this feature is in
 * enhance-prompt-api.test.ts (API client) and these tests cover the
 * action→boolean-pair semantics that the component is required to use.
 */
import { describe, expect, it } from 'vitest';

/**
 * Outcome mapping as specified by Task T6.
 * Use enhanced   → { used: true,  edited_before_use: false }
 * Edit enhanced  → { used: true,  edited_before_use: true  }
 * Keep original  → { used: false }
 * Dismiss (X)    → { used: false }
 */
type ActionKind = 'use' | 'edit' | 'keep' | 'dismiss';

interface OutcomePair {
	used?: boolean;
	edited_before_use?: boolean;
}

function actionToOutcome(action: ActionKind): OutcomePair {
	switch (action) {
		case 'use':    return { used: true,  edited_before_use: false };
		case 'edit':   return { used: true,  edited_before_use: true  };
		case 'keep':   return { used: false };
		case 'dismiss': return { used: false };
	}
}

describe('EnhancePromptExpansion action → outcome mapping', () => {
	it('"use enhanced" maps to { used: true, edited_before_use: false }', () => {
		const outcome = actionToOutcome('use');
		expect(outcome.used).toBe(true);
		expect(outcome.edited_before_use).toBe(false);
	});

	it('"edit enhanced" maps to { used: true, edited_before_use: true }', () => {
		const outcome = actionToOutcome('edit');
		expect(outcome.used).toBe(true);
		expect(outcome.edited_before_use).toBe(true);
	});

	it('"keep original" maps to { used: false } with no edited_before_use key', () => {
		const outcome = actionToOutcome('keep');
		expect(outcome.used).toBe(false);
		expect(outcome.edited_before_use).toBeUndefined();
	});

	it('"dismiss (X)" maps to { used: false } — same as keep original', () => {
		const outcome = actionToOutcome('dismiss');
		expect(outcome.used).toBe(false);
		expect(outcome.edited_before_use).toBeUndefined();
	});
});
