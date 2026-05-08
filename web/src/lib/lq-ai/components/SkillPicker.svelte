<script lang="ts">
	/**
	 * Skill-selection panel above the chat input.
	 *
	 * Multi-skill in a single message is allowed (PRD §3.4); attach order
	 * is preserved on the wire.
	 *
	 * When a skill is attached, its frontmatter inputs render as a form via
	 * `SkillInputForm`. Required inputs the user hasn't filled block submit.
	 *
	 * Project context inheritance: `projectAttachedSkills` are surfaced as
	 * already-attached and read-only; the user can still attach additional
	 * per-message skills.
	 */
	import type { Skill, SkillSummary } from '../types';
	import SkillInputForm from './SkillInputForm.svelte';

	export let availableSkills: SkillSummary[] = [];
	export let selectedSkillNames: string[] = [];
	export let projectAttachedSkills: string[] = [];
	export let skillDetails: Record<string, Skill> = {};
	export let skillInputs: Record<string, Record<string, unknown>> = {};

	export let onAttach: (name: string) => void = () => undefined;
	export let onDetach: (name: string) => void = () => undefined;
	export let onUpdateInputs: (name: string, values: Record<string, unknown>) => void = () =>
		undefined;

	let pickerOpen = false;
	let searchTerm = '';

	$: filteredAvailable = availableSkills
		.filter(
			(s) =>
				!selectedSkillNames.includes(s.name) &&
				!projectAttachedSkills.includes(s.name) &&
				(searchTerm === '' ||
					s.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
					s.title.toLowerCase().includes(searchTerm.toLowerCase()))
		)
		.sort((a, b) => a.title.localeCompare(b.title));
</script>

<div class="border border-gray-200 dark:border-gray-800 rounded-md p-3 space-y-2" data-testid="lq-ai-skill-picker">
	<div class="flex items-center justify-between">
		<span class="text-sm font-medium text-gray-700 dark:text-gray-200">Skills</span>
		<button
			type="button"
			class="text-xs px-2 py-1 rounded border border-indigo-300 text-indigo-700 hover:bg-indigo-50"
			on:click={() => (pickerOpen = !pickerOpen)}
			data-testid="lq-ai-skill-picker-toggle"
		>
			{pickerOpen ? 'Close' : '+ Skills'}
		</button>
	</div>

	{#if projectAttachedSkills.length > 0}
		<div class="text-xs text-gray-500">
			From project (auto-attached):
			<span class="space-x-1">
				{#each projectAttachedSkills as name}
					<span
						class="inline-block px-2 py-0.5 rounded-full bg-gray-100 text-gray-700 text-xs border border-gray-200"
						title="Inherited from this chat's Project"
					>
						{name}
					</span>
				{/each}
			</span>
		</div>
	{/if}

	{#if selectedSkillNames.length > 0}
		<div class="space-y-2">
			{#each selectedSkillNames as name (name)}
				<div class="rounded border border-indigo-200 bg-indigo-50 dark:bg-indigo-900/20 dark:border-indigo-800 p-2">
					<div class="flex items-center justify-between">
						<span class="text-sm font-medium text-indigo-900 dark:text-indigo-100">
							{skillDetails[name]?.title ?? name}
						</span>
						<button
							type="button"
							class="text-xs text-rose-600 hover:underline"
							on:click={() => onDetach(name)}
							data-testid={`lq-ai-skill-detach-${name}`}
						>
							Detach
						</button>
					</div>
					{#if skillDetails[name]}
						<div class="mt-1">
							<SkillInputForm
								inputs={skillDetails[name].inputs ?? []}
								values={skillInputs[name] ?? {}}
								onChange={(next) => onUpdateInputs(name, next)}
							/>
						</div>
					{:else}
						<p class="text-xs text-gray-500 italic mt-1">Loading skill details…</p>
					{/if}
				</div>
			{/each}
		</div>
	{/if}

	{#if pickerOpen}
		<div class="border-t border-gray-200 dark:border-gray-800 pt-2">
			<input
				type="text"
				placeholder="Search skills…"
				class="w-full text-sm border border-gray-300 rounded px-2 py-1 dark:bg-gray-800"
				bind:value={searchTerm}
				data-testid="lq-ai-skill-picker-search"
			/>
			<ul class="mt-2 max-h-48 overflow-y-auto divide-y divide-gray-100 dark:divide-gray-800">
				{#each filteredAvailable as s (s.name)}
					<li>
						<button
							type="button"
							class="w-full text-left px-2 py-1.5 hover:bg-gray-50 dark:hover:bg-gray-800"
							on:click={() => onAttach(s.name)}
							data-testid={`lq-ai-skill-attach-${s.name}`}
						>
							<div class="text-sm font-medium text-gray-800 dark:text-gray-100">
								{s.title}
							</div>
							{#if s.description}
								<div class="text-xs text-gray-500">{s.description}</div>
							{/if}
						</button>
					</li>
				{:else}
					<li class="text-xs text-gray-500 italic px-2 py-2">No matching skills.</li>
				{/each}
			</ul>
		</div>
	{/if}
</div>
