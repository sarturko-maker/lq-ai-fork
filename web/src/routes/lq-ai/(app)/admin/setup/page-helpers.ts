/**
 * Pure helpers for the guided setup wizard (/lq-ai/admin/setup — B-7b, ADR-F067
 * D4). Extracted so vitest can exercise the step machine + validation without a
 * SvelteKit runtime (the house pattern — no @testing-library/svelte).
 *
 * The wizard is a thin multi-step UI over the shipped profiles endpoints
 * (`profilesApi`): pick a profile → (name, blank only) → House Brief → review &
 * activate → done. The single mutation is `applyProfile`, which adopts the
 * profile's Library entries + binds them in one atomic transaction — the fix for
 * the G13 fresh-org cliff (bindings are inert until adopted).
 */
import type {
	ProfileApplyRequest,
	ProfileApplyResult,
	ProfileSummary
} from '$lib/lq-ai/api/profiles';
import type { StepDef } from '$lib/lq-ai/components/primitives/StepRail.svelte';

/** localStorage flag: the admin completed OR skipped the wizard on this browser,
 *  so it no longer auto-launches on the cockpit landing. */
export const SETUP_DISMISSED_KEY = 'lq-ai:setup-dismissed';

/** The closed unit-of-work vocabulary offered for a blank area — mirrors the
 *  manifest `UnitLabel` Literal (app/profiles/schema.py). The blank-apply body
 *  accepts free text server-side, but the wizard offers the shipped four. */
export const UNIT_LABELS = ['Matter', 'Project', 'Programme', 'Investigation'] as const;

/** Same slug shape as the manifest `SLUG_PATTERN` / `PracticeAreaCreate.key`. */
const SLUG_RE = /^[a-z][a-z0-9-]{1,62}[a-z0-9]$/;

export function isValidSlug(key: string): boolean {
	return SLUG_RE.test(key);
}

export type WizardStepKey = 'profile' | 'name' | 'brief' | 'review' | 'done';

/**
 * The ordered steps for a chosen profile kind. The `name` step exists only for
 * the `blank` profile (an area profile carries its identity in the manifest);
 * before a profile is chosen (`kind === null`) we show the area-shaped skeleton.
 */
export function wizardSteps(kind: 'area' | 'blank' | null): StepDef[] {
	const steps: StepDef[] = [{ key: 'profile', label: 'Choose a profile' }];
	if (kind === 'blank') steps.push({ key: 'name', label: 'Name the area' });
	steps.push(
		{ key: 'brief', label: 'House Brief' },
		{ key: 'review', label: 'Review & activate' },
		{ key: 'done', label: 'Done' }
	);
	return steps;
}

/** The blank area's identity, as the admin fills it on the `name` step. */
export interface BlankIdentity {
	targetKey: string;
	name: string;
	unitLabel: string;
}

/** All three blank fields present + the key a valid slug. */
export function blankIdentityComplete(id: BlankIdentity): boolean {
	return isValidSlug(id.targetKey.trim()) && id.name.trim() !== '' && id.unitLabel.trim() !== '';
}

/**
 * The apply body for a profile kind. An `area` profile sends `{}` (identity
 * comes from the manifest; sending any field is a 422); a `blank` profile sends
 * all three trimmed fields.
 */
export function buildApplyBody(kind: 'area' | 'blank', id: BlankIdentity): ProfileApplyRequest {
	if (kind === 'blank') {
		return {
			target_key: id.targetKey.trim(),
			name: id.name.trim(),
			unit_label: id.unitLabel.trim()
		};
	}
	return {};
}

/** State the per-step Next gate reads. */
export interface WizardGateState {
	selectedProfile: ProfileSummary | null;
	identity: BlankIdentity;
}

/**
 * Whether the current step's Next/primary control may proceed. `review` is the
 * apply screen — its own button owns the mutation, so the gate is permissive
 * there; adoption is "unskippable" only in that you cannot reach `done` without
 * a successful apply (the component advances on success, not on Next).
 */
export function canProceed(step: WizardStepKey, state: WizardGateState): boolean {
	switch (step) {
		case 'profile':
			return state.selectedProfile !== null;
		case 'name':
			return blankIdentityComplete(state.identity);
		case 'brief':
		case 'review':
		case 'done':
			return true;
	}
}

/** The sub-agent display names out of a manifest `agent_config` (`{subagents:
 *  [{name, …}]}`) — defensively, since `agent_config` is an opaque dict. */
export function rosterNames(agentConfig: Record<string, unknown>): string[] {
	const raw = (agentConfig as { subagents?: unknown }).subagents;
	if (!Array.isArray(raw)) return [];
	return raw
		.map((s) => (s && typeof s === 'object' ? String((s as { name?: unknown }).name ?? '') : ''))
		.filter((n) => n !== '');
}

/** Total capabilities newly adopted into the Library by an apply. */
export function adoptedCount(r: ProfileApplyResult): number {
	return Object.values(r.adopted).reduce((n, keys) => n + keys.length, 0);
}

export interface ApplyOutcome {
	headline: string;
	lines: string[];
}

/**
 * Human receipt for a successful apply. Keys the headline off `area_created`
 * (new area vs. activated existing — the fresh-org norm activates a seeded
 * area), and reports the adopted/roster/HITL counts. A re-apply that adds
 * nothing new (`on_conflict_do_nothing`) is success, not a no-op error — say so
 * plainly rather than rendering bare zeros.
 */
export function describeApplyOutcome(r: ProfileApplyResult, displayName: string): ApplyOutcome {
	const adopted = adoptedCount(r);
	const headline = r.area_created
		? `New area “${displayName}” is ready.`
		: `${displayName} is ready.`;

	const lines: string[] = [];
	if (adopted > 0) {
		lines.push(
			`${adopted} ${plural(adopted, 'capability', 'capabilities')} adopted into your Library.`
		);
	} else {
		lines.push('Everything this profile needs was already in your Library — nothing to add.');
	}
	if (r.roster_subagents > 0) {
		lines.push(
			`${r.roster_subagents} sub-${plural(r.roster_subagents, 'agent', 'agents')} in the roster.`
		);
	}
	if (r.hitl_tools > 0) {
		lines.push(`${r.hitl_tools} stop-and-ask ${plural(r.hitl_tools, 'tool', 'tools')} enabled.`);
	}
	return { headline, lines };
}

function plural(n: number, one: string, many: string): string {
	return n === 1 ? one : many;
}

/**
 * Whether the cockpit landing should auto-launch the setup wizard. True only for
 * a tenant-admin (the operator is fenced out of apply, ADR-F064) who has neither
 * completed nor skipped it on this browser, on an org whose Library is still
 * empty — the direct G13 signal (a fresh org's seeded bindings are inert until
 * something is adopted).
 */
export function shouldAutoLaunchSetup(p: {
	isAdmin: boolean;
	role: string | null | undefined;
	dismissed: boolean;
	libraryEmpty: boolean;
}): boolean {
	return p.isAdmin && p.role !== 'operator' && !p.dismissed && p.libraryEmpty;
}
