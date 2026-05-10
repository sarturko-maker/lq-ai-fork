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
			<h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">My skills</h1>
			<p class="text-xs text-gray-600 dark:text-gray-400 mt-1">
				Skills you've authored. A skill with a slug that matches a built-in shadows the built-in
				for your chats only — other users still see the built-in.
			</p>
		</div>
		<div class="flex gap-2">
			<a
				href="/lq-ai"
				class="text-xs px-3 py-2 rounded border border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800"
			>
				Back to chat
			</a>
			<a
				href="/lq-ai/skills/new"
				class="text-xs px-3 py-2 rounded bg-indigo-600 text-white hover:bg-indigo-500"
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
		<p class="text-sm text-gray-500">Loading…</p>
	{:else if rows.length === 0}
		<div
			class="p-6 rounded border border-dashed border-gray-300 dark:border-gray-700 text-center text-sm text-gray-500"
		>
			<p>You haven't created any skills yet.</p>
			<p class="mt-2">
				<a href="/lq-ai/skills/new" class="text-indigo-600 dark:text-indigo-400 underline">
					Create your first skill
				</a>
				, or fork a built-in from the picker.
			</p>
		</div>
	{:else}
		<div class="overflow-x-auto border border-gray-200 dark:border-gray-700 rounded">
			<table class="min-w-full text-sm">
				<thead class="bg-gray-50 dark:bg-gray-900 text-xs uppercase text-gray-500">
					<tr>
						<th class="text-left px-3 py-2">Title</th>
						<th class="text-left px-3 py-2">Slug</th>
						<th class="text-left px-3 py-2">Version</th>
						<th class="text-left px-3 py-2">Updated</th>
						<th class="text-right px-3 py-2">Actions</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-gray-100 dark:divide-gray-800">
					{#each rows as row (row.id)}
						<tr data-testid="lq-ai-user-skill-row">
							<td class="px-3 py-2 text-gray-900 dark:text-gray-100">
								<a
									href={`/lq-ai/skills/${row.id}/edit`}
									class="font-medium text-indigo-700 dark:text-indigo-300 hover:underline"
								>
									{row.display_name}
								</a>
								{#if row.description}
									<div class="text-xs text-gray-500 mt-0.5 line-clamp-1">{row.description}</div>
								{/if}
							</td>
							<td class="px-3 py-2">
								<code class="text-xs font-mono text-gray-700 dark:text-gray-300">{row.slug}</code>
								{#if builtinSlugs.has(row.slug)}
									<span
										class="ml-2 inline-flex items-center px-2 py-0.5 rounded text-[10px] uppercase tracking-wide bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100"
										title="This slug matches a built-in skill; your version takes effect in your chats."
										data-testid="lq-ai-user-skill-shadow-chip"
									>
										Shadows built-in
									</span>
								{/if}
							</td>
							<td class="px-3 py-2 text-gray-600 dark:text-gray-400 font-mono text-xs">{row.version}</td>
							<td class="px-3 py-2 text-xs text-gray-500">{shortDate(row.updated_at)}</td>
							<td class="px-3 py-2 text-right whitespace-nowrap">
								<a
									href={`/lq-ai/skills/${row.id}/edit`}
									class="text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800"
								>
									Edit
								</a>
								<button
									type="button"
									class="ml-1 text-xs px-2 py-1 rounded border border-rose-300 text-rose-700 hover:bg-rose-50 dark:border-rose-700 dark:text-rose-300 dark:hover:bg-rose-950"
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
