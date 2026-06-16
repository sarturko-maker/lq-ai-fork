/**
 * Top-tab definitions for the /lq-ai/* shell.
 *
 * Visibility = whether the user is allowed to see the tab at all (role gate).
 * Available  = whether the tab's destination route exists yet (per Wave A
 *              of the M1 frontend redesign; subsequent waves flip these to
 *              true as they ship the destination surfaces).
 *
 * Tabs that are visible-but-not-available open a ComingSoonModal that
 * points at the design spec.
 */

export type TabId =
	| 'home'
	| 'agents'
	| 'chats'
	| 'matters'
	| 'skills'
	| 'knowledge'
	| 'playbooks'
	| 'tabular'
	| 'saved-prompts'
	| 'learn'
	| 'autonomous'
	| 'admin';

/**
 * Presentational grouping for the tab bar's section separators + muted-legacy
 * styling (F2-M3). PURELY VISUAL — does not gate visibility, availability, or
 * order. `core` = everyday surfaces; `legacy` = the linear LangGraph executors
 * the fork replaces (playbooks, tabular); `gated` = role/pref-gated (admin,
 * autonomous). Forward-compatible with UX-A (de-emphasised here → retired there).
 * Absent ⇒ treated as `core`.
 */
export type TabGroup = 'core' | 'legacy' | 'gated';

export interface TabDef {
	id: TabId;
	label: string;
	icon: string; // emoji used in mockups; replaced with sprite in Wave F polish
	route: string;
	adminOnly?: boolean;
	available: boolean;
	/** The wave that lands the destination route. Used by ComingSoonModal copy. */
	shipsInWave?: 'B' | 'C' | 'D' | 'E';
	/** Presentational section (F2-M3) — see {@link TabGroup}. Absent ⇒ `core`. */
	group?: TabGroup;
}

/** The presentational group of a tab (defaults to `core`). */
export function tabGroupOf(tab: TabDef): TabGroup {
	return tab.group ?? 'core';
}

export interface User {
	id: string;
	email: string;
	is_admin: boolean;
	must_change_password: boolean;
	role?: 'admin' | 'member' | 'viewer';
}

export const TABS: readonly TabDef[] = [
	{ id: 'home', label: 'Home', icon: '🏠', route: '/lq-ai', available: true },
	// Deep-agent surface (F0-S3 preview; superseded as the area home by the
	// F1-S2 cockpit at /lq-ai — kept for regression value until fully retired).
	{ id: 'agents', label: 'Agents', icon: '⚖️', route: '/lq-ai/agents', available: true },
	{ id: 'chats', label: 'Chats', icon: '💬', route: '/lq-ai/chats', available: true },
	{ id: 'matters', label: 'Matters', icon: '📁', route: '/lq-ai/matters', available: true },
	{ id: 'skills', label: 'Skills', icon: '🛠️', route: '/lq-ai/skills', available: true },
	{ id: 'knowledge', label: 'Knowledge', icon: '📎', route: '/lq-ai/knowledge', available: true },
	{
		id: 'playbooks',
		label: 'Playbooks',
		icon: '📋',
		route: '/lq-ai/playbooks',
		available: true,
		group: 'legacy'
	},
	{
		id: 'tabular',
		label: 'Tabular',
		icon: '📊',
		route: '/lq-ai/tabular',
		available: true,
		group: 'legacy'
	},
	{
		id: 'saved-prompts',
		label: 'Saved Prompts',
		icon: '📌',
		route: '/lq-ai/saved-prompts',
		available: true
	},
	{ id: 'learn', label: 'Learn', icon: '📖', route: '/lq-ai/learn', available: true },
	{
		id: 'autonomous',
		label: 'Autonomous',
		icon: '🤖',
		route: '/lq-ai/autonomous',
		available: true,
		group: 'gated'
	},
	{
		id: 'admin',
		label: 'Admin',
		icon: '🛡',
		route: '/lq-ai/admin/audit-log',
		adminOnly: true,
		available: true,
		group: 'gated'
	}
] as const;

export interface TabVisibilityOpts {
	autonomousEnabled?: boolean;
}

/**
 * The tabs a user may see, role/pref-gated. Drives the cockpit rail's Tools
 * section + the header tool menu. (Lived in the now-retired `TopTabBar.svelte`
 * until UX-A-5; moved here — the legacy top-tab shell is gone, but the tab
 * vocabulary it defined is still the source of truth for the rail.)
 */
export function visibleTabsFor(user: User | null, opts: TabVisibilityOpts = {}): TabDef[] {
	return TABS.filter((t) => isTabVisible(t.id, user, opts));
}

export function isTabVisible(id: TabId, user: User | null, opts: TabVisibilityOpts = {}): boolean {
	const tab = TABS.find((t) => t.id === id);
	if (!tab) return false;
	if (id === 'autonomous') return opts.autonomousEnabled === true;
	if (tab.adminOnly) {
		return user?.role === 'admin' || user?.is_admin === true;
	}
	return true;
}

export function isTabAvailable(id: TabId): boolean {
	return TABS.find((t) => t.id === id)?.available ?? false;
}

/** Returns the tab whose route is the deepest prefix of pathname, or null on auth-exempt routes. */
export function activeTabFor(pathname: string): TabId | null {
	if (pathname === '/lq-ai/login' || pathname === '/lq-ai/change-password') return null;
	if (pathname === '/lq-ai' || pathname === '/lq-ai/') return 'home';

	// Find tab whose route is the deepest prefix.
	let best: TabDef | null = null;
	for (const tab of TABS) {
		if (tab.id === 'home') continue;
		if (pathname === tab.route || pathname.startsWith(tab.route + '/')) {
			if (!best || tab.route.length > best.route.length) best = tab;
		}
	}
	return best?.id ?? 'home';
}
