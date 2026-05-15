<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import TrustPill from './TrustPill.svelte';
	import { auth } from '../auth/store';
	import { getUsage } from '../api/admin';
	import { LQAIApiError } from '../api/client';
	import type { TrustVariant } from './TrustPill.svelte';

	// Providers whose turns count as self-hosted (not external).
	const SELF_HOSTED_MARKERS = new Set(['ollama', 'localhost', 'ollama-localhost']);

	type CardState =
		| { kind: 'not-admin' }
		| { kind: 'loading' }
		| { kind: 'ready'; today: number; sevenDay: number }
		| { kind: 'error'; message: string };

	let state: CardState = { kind: 'loading' };

	function isAdmin(): boolean {
		const user = get(auth).user;
		// Spec §4.1.1: prefer role === 'admin'; fall back to is_admin boolean.
		return user?.role === 'admin' || user?.is_admin === true;
	}

	function todayMidnightISO(): string {
		const d = new Date();
		d.setHours(0, 0, 0, 0);
		return d.toISOString();
	}

	function sevenDaysAgoISO(): string {
		const d = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
		d.setHours(0, 0, 0, 0);
		return d.toISOString();
	}

	function sumExternal(rows: { group_key: string; request_count: number }[]): number {
		return rows
			.filter((r) => !SELF_HOSTED_MARKERS.has(r.group_key.toLowerCase()))
			.reduce((acc, r) => acc + r.request_count, 0);
	}

	onMount(async () => {
		if (!isAdmin()) {
			state = { kind: 'not-admin' };
			return;
		}

		try {
			const [todayRes, sevenDayRes] = await Promise.all([
				getUsage({ group_by: 'provider', date_from: todayMidnightISO() }),
				getUsage({ group_by: 'provider', date_from: sevenDaysAgoISO() })
			]);
			state = {
				kind: 'ready',
				today: sumExternal(todayRes.rows),
				sevenDay: sumExternal(sevenDayRes.rows)
			};
		} catch (e) {
			// Race: user token expired or role changed since page load.
			if (e instanceof LQAIApiError && e.status === 403) {
				state = { kind: 'not-admin' };
			} else {
				state = { kind: 'error', message: 'Usage data unavailable. Try refreshing.' };
			}
		}
	});

	function pillVariant(count: number): TrustVariant {
		return count > 100 ? 'warn' : 'audit';
	}
</script>

<div class="lq-card">
	<h3 class="lq-text-panel-h card-title">External-turn usage</h3>

	{#if state.kind === 'not-admin'}
		<p class="lq-text-body gated-msg">External-turn counts are visible to admins only.</p>
		<p class="lq-text-caption gated-why">
			These figures come from /admin/usage, which is admin-gated for cost-disclosure reasons.
		</p>
	{:else if state.kind === 'loading'}
		<p class="lq-text-body loading-msg">Loading usage data…</p>
	{:else if state.kind === 'error'}
		<p class="lq-text-body error-msg">{state.message}</p>
	{:else if state.kind === 'ready'}
		<div class="stats-row">
			<div class="stat-block">
				<span class="stat-count">{state.today}</span>
				<span class="lq-text-caption stat-label">Today</span>
				<TrustPill variant={pillVariant(state.today)} label="external turns" />
			</div>
			<div class="stat-divider" aria-hidden="true"></div>
			<div class="stat-block">
				<span class="stat-count">{state.sevenDay}</span>
				<span class="lq-text-caption stat-label">Last 7 days</span>
				<TrustPill variant={pillVariant(state.sevenDay)} label="external turns" />
			</div>
		</div>
		<p class="lq-text-caption footer-note">
			"External" = any turn routed to a non-self-hosted provider (excludes ollama / localhost).
		</p>
	{/if}
</div>

<style>
	.lq-card {
		background: var(--lq-canvas);
		border: 1px solid var(--lq-border);
		border-radius: var(--lq-radius-lg);
		padding: var(--lq-space-5);
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-3);
	}

	.card-title {
		margin: 0;
	}

	.gated-msg {
		color: var(--lq-text-secondary);
	}

	.gated-why {
		color: var(--lq-text-tertiary);
	}

	.loading-msg,
	.error-msg {
		color: var(--lq-text-secondary);
	}

	.stats-row {
		display: flex;
		align-items: flex-start;
		gap: var(--lq-space-6);
	}

	.stat-block {
		display: flex;
		flex-direction: column;
		gap: var(--lq-space-1);
	}

	.stat-count {
		font-size: 28px;
		font-weight: 600;
		color: var(--lq-text);
		line-height: 1.1;
	}

	.stat-label {
		color: var(--lq-text-secondary);
	}

	.stat-divider {
		width: 1px;
		background: var(--lq-border);
		align-self: stretch;
		margin-top: 4px;
	}

	.footer-note {
		color: var(--lq-text-tertiary);
		margin: 0;
	}
</style>
