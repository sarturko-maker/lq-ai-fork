/**
 * Cockpit v0 helpers — F1-S2 (ADR-F002 "glass cockpit").
 *
 * Pure logic only (unit-tested): URL-state codec for the single cockpit
 * route, view derivation, relative-time formatting, and the theme cycle.
 * Area keys live ONLY in URL/presentation state here — never written to
 * stored rows until S3's real schema lands (MILESTONES pre-F1 guard).
 */

/** Selection state carried in `/lq-ai` search params — deep-linkable. */
export interface CockpitState {
	/** Practice-area key ('commercial', …) — presentation-only until S3. */
	area: string | null;
	/** Selected matter (project id). */
	matter: string | null;
	/** Conversation to resume; null = fresh composer in the matter. */
	thread: string | null;
	/** The "unfiled conversations" bucket is open. */
	unfiled: boolean;
}

export type CockpitView = 'areas' | 'matters' | 'matter' | 'unfiled';

export function parseCockpitState(params: URLSearchParams): CockpitState {
	return {
		area: params.get('area'),
		matter: params.get('matter'),
		thread: params.get('thread'),
		unfiled: params.get('view') === 'unfiled'
	};
}

/** Build the cockpit URL for a selection (omits empty params). */
export function cockpitUrl(state: Partial<CockpitState>): string {
	const params = new URLSearchParams();
	if (state.unfiled) {
		params.set('view', 'unfiled');
		if (state.thread) params.set('thread', state.thread);
	} else {
		if (state.area) params.set('area', state.area);
		if (state.matter) params.set('matter', state.matter);
		if (state.thread) params.set('thread', state.thread);
	}
	const qs = params.toString();
	return `/lq-ai${qs ? `?${qs}` : ''}`;
}

/**
 * Which main-pane view a selection renders. The cockpit LANDS on the
 * area list (MILESTONES § F1 — no auto-landing in Commercial).
 */
export function viewOf(state: CockpitState): CockpitView {
	if (state.unfiled) return 'unfiled';
	if (state.matter) return 'matter';
	if (state.area) return 'matters';
	return 'areas';
}

/** Compact relative timestamp for list rows ('12m ago', 'yesterday'). */
export function timeAgo(iso: string | null, nowMs: number): string {
	if (!iso) return '—';
	const then = Date.parse(iso);
	if (Number.isNaN(then)) return '—';
	const diff = nowMs - then;
	if (diff < 60_000) return 'just now';
	const minutes = Math.floor(diff / 60_000);
	if (minutes < 60) return `${minutes}m ago`;
	const hours = Math.floor(minutes / 60);
	if (hours < 24) return `${hours}h ago`;
	const days = Math.floor(hours / 24);
	if (days === 1) return 'yesterday';
	if (days < 30) return `${days}d ago`;
	return new Date(then).toLocaleDateString();
}

/** Per-area rollup for the area cards (F1-S3). */
export interface AreaActivity {
	count: number;
	lastActivity: string | null;
}

/** Minimal shape the area-grouping helpers read off a matter. */
interface AreaFileable {
	practice_area_key: string | null;
}

/**
 * Group matters by their practice-area key for the area-card rollups
 * (F1-S3). Matters arrive most-recent-activity first, so the FIRST match
 * per area carries its latest activity. Unfiled matters (null key) are
 * skipped — they live in the cockpit's unfiled bucket, not under an area.
 */
export function areaActivityCounts<T extends AreaFileable & { last_run_at: string | null }>(
	matters: T[]
): Map<string, AreaActivity> {
	const map = new Map<string, AreaActivity>();
	for (const m of matters) {
		if (!m.practice_area_key) continue;
		const cur = map.get(m.practice_area_key);
		if (cur) {
			cur.count += 1;
			cur.lastActivity ??= m.last_run_at;
		} else {
			map.set(m.practice_area_key, { count: 1, lastActivity: m.last_run_at });
		}
	}
	return map;
}

/** The matters that file under one area (F1-S3 — by practice_area_key). */
export function mattersForArea<T extends AreaFileable>(matters: T[], areaKey: string): T[] {
	return matters.filter((m) => m.practice_area_key === areaKey);
}

export type Theme = 'light' | 'dark' | 'system';

/** Toggle order: system → light → dark → system. */
export function nextTheme(current: Theme): Theme {
	switch (current) {
		case 'system':
			return 'light';
		case 'light':
			return 'dark';
		case 'dark':
			return 'system';
	}
}

export function normalizeTheme(raw: string | null): Theme {
	// app.html contract: 'system' follows the OS, 'light' is light,
	// anything else (incl. legacy 'dark'/'oled-dark') renders dark.
	if (raw === null || raw === 'system') return 'system';
	if (raw === 'light') return 'light';
	return 'dark';
}

/**
 * Persist + apply a theme choice. Mirrors the app.html pre-paint script
 * (same storage key, same class semantics, same token canvas colors for
 * the meta) so a reload reproduces exactly what the toggle applied.
 */
export function applyTheme(theme: Theme): void {
	localStorage.setItem('theme', theme);
	const dark =
		theme === 'system'
			? window.matchMedia('(prefers-color-scheme: dark)').matches
			: theme === 'dark';
	const root = document.documentElement;
	root.classList.remove('dark', 'light');
	root.classList.add(dark ? 'dark' : 'light');
	const meta = document.querySelector('meta[name="theme-color"]');
	if (meta) meta.setAttribute('content', dark ? '#1b1e24' : '#f4f3f0');
}

/**
 * Motion gate: component transitions pass their durations through here so
 * `prefers-reduced-motion: reduce` collapses them to 0 (svelte transitions
 * don't respect the media query on their own).
 */
export function motionMs(ms: number): number {
	if (typeof matchMedia === 'undefined') return ms;
	return matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : ms;
}
