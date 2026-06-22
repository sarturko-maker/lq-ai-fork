<script lang="ts">
	/**
	 * Read-only disclosure of a practice area's configuration (UX-B-5).
	 *
	 * The transparency rule (CLAUDE.md): "every prompt, skill, agent instruction
	 * and tool grant must be readable in the UI or the source." This surfaces,
	 * collapsed by default, an area's PROFILE (the operator-authored identity
	 * folded into the agent's system prompt), its BOUND SKILLS, and its declared
	 * SUBAGENTS (name + description + each one's own skill subset, ADR-F016/F017).
	 *
	 * Everything here is data already on the wire (`GET /practice-areas` returns
	 * profile_md + bound_skills + agent_config). It is shown honestly: it is what
	 * the agent CAN do (its configured surface), not a promise of what it will do
	 * — a tier-4 model often won't delegate at small matter sizes (UX-B-4).
	 */
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down';
	import FileTextIcon from '@lucide/svelte/icons/file-text';
	import WrenchIcon from '@lucide/svelte/icons/wrench';
	import UsersIcon from '@lucide/svelte/icons/users';

	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import { renderModelMarkdown } from '$lib/lq-ai/sanitize-markdown';
	import { areaSubagents } from './helpers';

	let { area }: { area: PracticeArea } = $props();

	const subagents = $derived(areaSubagents(area.agent_config));
	// The profile is operator-authored, but we render it through the SAME
	// sanitising sink as model output (one media-forbid policy, no drift).
	const profileHtml = $derived(area.profile_md ? renderModelMarkdown(area.profile_md) : '');
</script>

<details class="ac" data-testid="lq-cockpit-area-config">
	<summary class="ac__trigger">
		<span class="ac__label">How this area works</span>
		<span class="ac__chevron"><ChevronDownIcon class="size-4" aria-hidden="true" /></span>
	</summary>
	<div class="ac__body">
		{#if profileHtml}
			<section class="ac__section">
				<h3 class="ac__heading">
					<FileTextIcon class="size-3.5" aria-hidden="true" />
					Profile
				</h3>
				<div class="ac__prose prose prose-sm dark:prose-invert max-w-none">
					<!-- eslint-disable-next-line svelte/no-at-html-tags — renderModelMarkdown-sanitized -->
					{@html profileHtml}
				</div>
			</section>
		{/if}

		<section class="ac__section">
			<h3 class="ac__heading">
				<WrenchIcon class="size-3.5" aria-hidden="true" />
				Skills
			</h3>
			{#if area.bound_skills.length > 0}
				<ul class="ac__chips" data-testid="lq-cockpit-area-skills">
					{#each area.bound_skills as skill (skill)}
						<li class="ac__chip">{skill}</li>
					{/each}
				</ul>
			{:else}
				<p class="ac__empty">
					No skills bound — the agent answers from documents and its own reasoning.
				</p>
			{/if}
		</section>

		<section class="ac__section">
			<h3 class="ac__heading">
				<UsersIcon class="size-3.5" aria-hidden="true" />
				Subagents
			</h3>
			{#if subagents.length > 0}
				<ul class="ac__subagents" data-testid="lq-cockpit-area-subagents">
					{#each subagents as sub (sub.name)}
						<li class="ac__subagent">
							<p class="ac__subagent-name">{sub.name}</p>
							{#if sub.description}
								<p class="ac__subagent-desc">{sub.description}</p>
							{/if}
							{#if sub.skills.length > 0}
								<ul class="ac__chips ac__chips--inset">
									{#each sub.skills as skill (skill)}
										<li class="ac__chip">{skill}</li>
									{/each}
								</ul>
							{/if}
						</li>
					{/each}
				</ul>
				<p class="ac__note">
					The agent delegates to a subagent on demand — for a complex, multi-document {area.unit_label.toLowerCase()};
					a short document it reads directly.
				</p>
			{:else}
				<p class="ac__empty">
					No subagents — the area's agent does the work itself, fanning out to its own tools.
				</p>
			{/if}
		</section>
	</div>
</details>

<style>
	.ac {
		margin-top: 0.75rem;
		border: 1px solid var(--border);
		border-radius: var(--radius-lg);
		background: var(--card);
	}
	.ac__trigger {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		padding: 0.625rem 0.875rem;
		cursor: pointer;
		list-style: none;
		color: var(--muted-foreground);
		transition: color var(--motion-fast) var(--ease-out);
	}
	.ac__trigger::-webkit-details-marker {
		display: none;
	}
	.ac__trigger:hover {
		color: var(--foreground);
	}
	.ac__label {
		font-size: 0.8125rem;
		font-weight: 500;
	}
	.ac__chevron {
		display: inline-flex;
		flex-shrink: 0;
		transition: transform var(--motion-fast) var(--ease-out);
	}
	.ac[open] .ac__chevron {
		transform: rotate(180deg);
	}
	.ac__body {
		display: flex;
		flex-direction: column;
		gap: 1rem;
		padding: 0 0.875rem 0.875rem;
	}
	.ac__section {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	.ac__heading {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--muted-foreground);
	}
	.ac__prose {
		color: var(--foreground);
	}
	.ac__chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.375rem;
	}
	.ac__chips--inset {
		margin-top: 0.375rem;
	}
	.ac__chip {
		padding: 0.125rem 0.5rem;
		border: 1px solid var(--border);
		border-radius: 9999px;
		font-size: 0.75rem;
		font-family: var(--font-mono, ui-monospace, monospace);
		color: var(--foreground);
		background: var(--muted);
	}
	.ac__empty {
		font-size: 0.8125rem;
		color: var(--muted-foreground);
	}
	.ac__subagents {
		display: flex;
		flex-direction: column;
		gap: 0.625rem;
	}
	.ac__subagent {
		padding: 0.625rem 0.75rem;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		background: var(--background);
	}
	.ac__subagent-name {
		font-size: 0.8125rem;
		font-weight: 600;
		font-family: var(--font-mono, ui-monospace, monospace);
		color: var(--foreground);
	}
	.ac__subagent-desc {
		margin-top: 0.25rem;
		font-size: 0.8125rem;
		color: var(--muted-foreground);
	}
	.ac__note {
		font-size: 0.75rem;
		color: var(--muted-foreground);
	}
</style>
