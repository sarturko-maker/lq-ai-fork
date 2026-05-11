<script lang="ts">
	/**
	 * /lq-ai/skills — Skill Creator landing page (D8 / ADR 0012).
	 *
	 * Lists the caller's DB-backed user-scope skills with edit / archive
	 * affordances. Empty state nudges toward "New skill". A user-scope
	 * skill at the same slug as a built-in shadows the built-in for that
	 * user's chats (per ADR 0012); the shadow indicator surfaces here so
	 * the user can see at-a-glance which of their skills are overriding.
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	import { userSkillsApi, skillsApi } from '$lib/lq-ai/api';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import type { UserSkill, SkillSummary } from '$lib/lq-ai/types';
	import TrustPill from '$lib/lq-ai/components/TrustPill.svelte';

	let rows: UserSkill[] = [];
	let builtinSlugs = new Set<string>();
	let loading = false;
	let listError: string | null = null;
	let actionError: string | null = null;

	async function load(): Promise<void> {
		loading = true;
		listError = null;
		try {
			const [mine, builtins] = await Promise.all([
				userSkillsApi.listUserSkills(),
				skillsApi.listSkills('builtin')
			]);
			rows = mine;
			builtinSlugs = new Set(builtins.map((s: SkillSummary) => s.name));
		} catch (e) {
			console.error('user-skills: load failed', e);
			listError =
				e instanceof LQAIApiError
					? e.message
					: e instanceof Error
						? e.message
						: 'Failed to load your skills.';
		} finally {
			loading = false;
		}
	}

	async function archive(row: UserSkill): Promise<void> {
		const confirmed = window.confirm(
			`Archive "${row.display_name}"? You can recreate at the same slug afterwards.`
		);
		if (!confirmed) return;
		actionError = null;
		try {
			await userSkillsApi.deleteUserSkill(row.id);
			rows = rows.filter((r) => r.id !== row.id);
		} catch (e) {
			console.error('user-skills: archive failed', e);
			actionError = e instanceof Error ? e.message : 'Failed to archive skill.';
		}
	}

	function shortDate(iso: string): string {
		try {
			return new Date(iso).toLocaleString();
		} catch {
			return iso;
		}
	}

	onMount(() => {
		load();
	});
</script>

<div class="p-4 max-w-5xl mx-auto" data-testid="lq-ai-user-skills">
	<header class="mb-4 flex items-center justify-between">
		<div>
			<h1 class="lq-text-page-h">My skills</h1>
			<p class="lq-text-caption mt-1" style="color: var(--lq-text-tertiary);">
				Skills you've authored. A skill with a slug that matches a built-in shadows the built-in
				for your chats only — other users still see the built-in.
			</p>
		</div>
		<div class="flex gap-2">
			<a
				href="/lq-ai"
				class="lq-btn-secondary text-xs"
			>
				Back to chat
			</a>
			<a
				href="/lq-ai/skills/new"
				class="lq-btn-primary text-xs"
				data-testid="lq-ai-user-skills-new-link"
			>
				+ New skill
			</a>
		</div>
	</header>

	{#if listError}
		<div
			class="mb-4 p-3 rounded border border-rose-300 bg-rose-50 text-rose-900 text-sm dark:border-rose-700 dark:bg-rose-950 dark:text-rose-100"
			role="alert"
		>
			{listError}
		</div>
	{/if}
	{#if actionError}
		<div
			class="mb-4 p-3 rounded border border-rose-300 bg-rose-50 text-rose-900 text-sm dark:border-rose-700 dark:bg-rose-950 dark:text-rose-100"
			role="alert"
		>
			{actionError}
		</div>
	{/if}

	{#if loading}
		<p class="lq-text-body" style="color: var(--lq-text-secondary);">Loading…</p>
	{:else if rows.length === 0}
		<div
			class="lq-empty-state p-6 text-center"
		>
			<p class="lq-text-body" style="color: var(--lq-text-secondary);">You haven't created any skills yet.</p>
			<p class="mt-2 lq-text-body">
				<a href="/lq-ai/skills/new" class="lq-link">
					Create your first skill
				</a>
				, or fork a built-in from the picker.
			</p>
		</div>
	{:else}
		<div class="lq-table-wrap overflow-x-auto">
			<table class="min-w-full lq-text-body-sm">
				<thead class="lq-thead">
					<tr>
						<th class="text-left px-3 py-2 lq-text-label">Title</th>
						<th class="text-left px-3 py-2 lq-text-label">Slug</th>
						<th class="text-left px-3 py-2 lq-text-label">Version</th>
						<th class="text-left px-3 py-2 lq-text-label">Updated</th>
						<th class="text-right px-3 py-2 lq-text-label">Actions</th>
					</tr>
				</thead>
				<tbody class="lq-tbody">
					{#each rows as row (row.id)}
						<tr data-testid="lq-ai-user-skill-row">
							<td class="px-3 py-2" style="color: var(--lq-text);">
								<a
									href={`/lq-ai/skills/${row.id}/edit`}
									class="font-medium lq-link hover:underline"
								>
									{row.display_name}
								</a>
								{#if row.description}
									<div class="lq-text-caption mt-0.5 line-clamp-1" style="color: var(--lq-text-tertiary);">{row.description}</div>
								{/if}
							</td>
							<td class="px-3 py-2">
								<code class="lq-text-caption font-mono" style="color: var(--lq-text-secondary);">{row.slug}</code>
								{#if builtinSlugs.has(row.slug)}
									<span class="ml-2" data-testid="lq-ai-user-skill-shadow-chip">
										<TrustPill
											variant="tier"
											label="Shadows built-in"
										/>
									</span>
								{/if}
							</td>
							<td class="px-3 py-2 lq-tabular lq-text-caption" style="color: var(--lq-text-secondary);">{row.version}</td>
							<td class="px-3 py-2 lq-text-caption" style="color: var(--lq-text-tertiary);">{shortDate(row.updated_at)}</td>
							<td class="px-3 py-2 text-right whitespace-nowrap">
								<a
									href={`/lq-ai/skills/${row.id}/edit`}
									class="lq-btn-secondary lq-text-caption"
								>
									Edit
								</a>
								<button
									type="button"
									class="ml-1 lq-btn-danger lq-text-caption"
									on:click={() => archive(row)}
									data-testid="lq-ai-user-skill-archive-btn"
								>
									Archive
								</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>

<style>
	.lq-btn-primary {
		background: var(--lq-accent);
		color: white;
		border: 0;
		border-radius: var(--lq-radius);
		padding: 8px 16px;
		font-size: 14px;
		font-weight: 500;
		cursor: pointer;
		text-decoration: none;
		display: inline-flex;
		align-items: center;
	}

	.lq-btn-secondary {
		background: transparent;
		color: var(--lq-text-secondary);
		border: 1px solid var(--lq-border);
		border-radius: var(--lq-radius);
		padding: 6px 12px;
		font-size: 12px;
		cursor: pointer;
		text-decoration: none;
		display: inline-flex;
		align-items: center;
	}
	.lq-btn-secondary:hover { background: var(--lq-inset); }

	.lq-btn-danger {
		background: transparent;
		color: var(--lq-error);
		border: 1px solid var(--lq-error);
		border-radius: var(--lq-radius);
		padding: 6px 12px;
		font-size: 12px;
		cursor: pointer;
	}
	.lq-btn-danger:hover { background: var(--lq-error-soft); }

	.lq-link {
		color: var(--lq-accent);
		text-decoration: none;
	}
	.lq-link:hover { text-decoration: underline; }

	.lq-empty-state {
		border-radius: var(--lq-radius-lg);
		border: 1px dashed var(--lq-border);
		padding: var(--lq-space-6);
	}

	.lq-table-wrap {
		border-radius: var(--lq-radius-lg);
		border: 1px solid var(--lq-border);
	}

	.lq-thead {
		background: var(--lq-inset);
	}

	.lq-tbody tr {
		border-top: 1px solid var(--lq-border);
	}
</style>
