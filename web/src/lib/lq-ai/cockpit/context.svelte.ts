/**
 * Cockpit shell context (UX-A-1, ADR-F014).
 *
 * The shell layout (`(app)/+layout.svelte`) owns the data the persistent rail
 * needs — practice areas + the matters/unfiled activity rollup + a shared
 * `nowMs` clock — and shares it with whatever renders in the canvas (the
 * landing today; tool surfaces in later UX-A slices) via Svelte CONTEXT, not a
 * module singleton: the state is scoped to the shell instance and torn down
 * when you leave `(app)` (e.g. sign-out → /login), so it can never leak one
 * user's matters to the next session in the same tab.
 *
 * All reads are settled rows (ADR-F004); provider/area keys stay presentation
 * state. No `load` functions — the app fetches client-side with the session
 * token (the established cockpit pattern).
 */
import { getContext, setContext } from 'svelte';

import { agentsApi, practiceAreasApi } from '$lib/lq-ai/api';
import { LQAIApiError } from '$lib/lq-ai/api/client';
import type { MatterActivityResponse } from '$lib/lq-ai/api/agents';
import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';

function errText(e: unknown): string {
	return e instanceof LQAIApiError ? e.message : 'network error';
}

/** Reactive shell state shared rail ↔ canvas. Instantiated once per shell. */
export class CockpitShellState {
	areas = $state<PracticeArea[] | null>(null);
	areasError = $state<string | null>(null);
	activity = $state<MatterActivityResponse | null>(null);
	activityError = $state<string | null>(null);
	/** Server-derived 'now' for relative times (the layout ticks it). */
	nowMs = $state(Date.now());
	/**
	 * The in-app Word editor is open in the canvas (ADR-F047, Slice 4). The
	 * canvas (ConversationHost) sets this; the shell layout reacts by gracefully
	 * collapsing the practice-area rail so the conversation + editor get the full
	 * width, then restoring the rail when the editor closes. A shared signal
	 * (not a callback) because the editor and the rail live in different parts of
	 * the shell tree.
	 */
	editorOpen = $state(false);

	async loadAreas(): Promise<void> {
		try {
			this.areas = (await practiceAreasApi.listPracticeAreas()).practice_areas;
			this.areasError = null;
		} catch (e: unknown) {
			this.areasError = errText(e);
		}
	}

	async loadActivity(): Promise<void> {
		try {
			this.activity = await agentsApi.listMatters();
			this.activityError = null;
		} catch (e: unknown) {
			this.activityError = errText(e);
		}
	}
}

const KEY = Symbol('lq-cockpit-state');

export function setCockpitState(state: CockpitShellState): CockpitShellState {
	return setContext(KEY, state);
}

export function getCockpitState(): CockpitShellState {
	return getContext(KEY) as CockpitShellState;
}
