<script lang="ts">
	/**
	 * /lq-ai/skills/new — create a new user-scope skill (D8 / ADR 0012).
	 *
	 * The form fields map 1:1 to UserSkillCreate. The slug input watches
	 * for collisions with filesystem-canonical built-ins and surfaces
	 * a yellow inline note so the user knows their skill will shadow the
	 * built-in for their chats. Collision is permitted (forking-by-
	 * shadowing per PRD §1.3 transparency); the note exists to make the
	 * behavior comprehensible, not to block.
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	import { userSkillsApi, skillsApi } from '$lib/lq-ai/api';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import type { SkillSummary } from '$lib/lq-ai/types';

	const SLUG_RE = /^[a-z0-9]([a-z0-9-]{0,78}[a-z0-9])?$/;

	let slug = '';
	let displayName = '';
	let description = '';
	let version = '1.0.0';
	let tagsInput = '';
	let body = '';
	let submitting = false;
	let submitError: string | null = null;
	let builtinSlugs = new Set<string>();
	let loadError: string | null = null;

	$: trimmedSlug = slug.trim();
	$: slugIsValid = trimmedSlug.length > 0 && SLUG_RE.test(trimmedSlug);
	$: shadowsBuiltIn = slugIsValid && builtinSlugs.has(trimmedSlug);
	$: canSubmit =
		!submitting &&
		slugIsValid &&
		displayName.trim().length > 0 &&
		description.trim().length > 0 &&
		body.trim().length > 0;

	async function loadBuiltins(): Promise<void> {
		try {
			const builtins = await skillsApi.listSkills('builtin');
			builtinSlugs = new Set(builtins.map((s: SkillSummary) => s.name));
		} catch (e) {
			console.error('user-skills/new: failed to load built-ins for shadow check', e);
			loadError =
				'Could not load the built-in skill list to check for shadow collisions. You can still create the skill; the shadow indicator just won\'t appear.';
		}
	}

	function parseTags(raw: string): string[] {
		return raw
			.split(',')
			.map((t) => t.trim())
			.filter((t) => t.length > 0);
	}

	async function submit(): Promise<void> {
		if (!canSubmit) return;
		submitting = true;
		submitError = null;
		try {
			const created = await userSkillsApi.createUserSkill({
				slug: trimmedSlug,
				display_name: displayName.trim(),
				description: description.trim(),
				body,
				version: version.trim() || '1.0.0',
				tags: parseTags(tagsInput)
			});
			goto(`/lq-ai/skills/${created.id}/edit?created=1`);
		} catch (e) {
			console.error('user-skills/new: create failed', e);
			if (e instanceof LQAIApiError && e.status === 409) {
				submitError =
					'You already have a skill with this slug. Pick a different slug or archive the existing one first.';
			} else {
				submitError = e instanceof Error ? e.message : 'Failed to create the skill.';
			}
		} finally {
			submitting = false;
		}
	}

	onMount(() => {
		loadBuiltins();
	});
</script>

<div class="p-4 max-w-3xl mx-auto" data-testid="lq-ai-user-skill-new">
	<header class="mb-4 flex items-center justify-between">
		<div>
			<h1 class="lq-text-page-h">New skill</h1>
			<p class="lq-text-caption mt-1" style="color: var(--lq-text-tertiary);">
				Author a skill that lives in your account. It shapes the system prompt for any chat where
				you attach it.
			</p>
		</div>
		<a
			href="/lq-ai/skills"
			class="lq-btn-secondary lq-text-caption"
		>
			Cancel
		</a>
	</header>

	{#if loadError}
		<div
			class="mb-4 p-3 rounded border border-amber-300 bg-amber-50 text-amber-900 text-xs dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100"
			role="status"
		>
			{loadError}
		</div>
	{/if}
	{#if submitError}
		<div
			class="mb-4 p-3 rounded border border-rose-300 bg-rose-50 text-rose-900 text-sm dark:border-rose-700 dark:bg-rose-950 dark:text-rose-100"
			role="alert"
		>
			{submitError}
		</div>
	{/if}

	<form
		class="space-y-4"
		on:submit|preventDefault={submit}
		data-testid="lq-ai-user-skill-new-form"
	>
		<label class="block">
			<span class="lq-text-label">Slug</span>
			<input
				type="text"
				bind:value={slug}
				placeholder="my-nda-review"
				required
				maxlength="80"
				class="mt-1 w-full rounded border-gray-300 dark:border-gray-700 dark:bg-gray-900 text-sm font-mono"
				data-testid="lq-ai-user-skill-new-slug"
			/>
			<p class="lq-text-caption mt-1" style="color: var(--lq-text-tertiary);">
				Lowercase, alphanumeric, hyphens. Used as the stable identifier the chat picker references.
			</p>
			{#if trimmedSlug.length > 0 && !slugIsValid}
				<p class="lq-text-caption mt-1" style="color: var(--lq-error);" data-testid="lq-ai-user-skill-new-slug-invalid">
					Slug must be lowercase, start and end with an alphanumeric, and use only letters, digits,
					and hyphens.
				</p>
			{/if}
			{#if shadowsBuiltIn}
				<div
					class="mt-2 p-2 rounded border border-amber-300 bg-amber-50 text-amber-900 text-xs dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100"
					data-testid="lq-ai-user-skill-new-shadow-warning"
					role="status"
				>
					<strong>Heads up — this shadows a built-in.</strong> When you reference
					<code class="font-mono">{trimmedSlug}</code> in a chat,
					<em>your</em> version will shape the prompt instead of the built-in. Other users still
					see the built-in. Pick a different slug if you want both to coexist for you.
				</div>
			{/if}
		</label>

		<label class="block">
			<span class="lq-text-label">Display name</span>
			<input
				type="text"
				bind:value={displayName}
				placeholder="My NDA Review"
				required
				maxlength="200"
				class="mt-1 w-full rounded border-gray-300 dark:border-gray-700 dark:bg-gray-900 text-sm"
			/>
		</label>

		<label class="block">
			<span class="lq-text-label">Description</span>
			<input
				type="text"
				bind:value={description}
				placeholder="One-sentence summary of when to use this skill."
				required
				maxlength="2000"
				class="mt-1 w-full rounded border-gray-300 dark:border-gray-700 dark:bg-gray-900 text-sm"
			/>
		</label>

		<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
			<label class="block">
				<span class="lq-text-label">Version</span>
				<input
					type="text"
					bind:value={version}
					placeholder="1.0.0"
					maxlength="50"
					class="mt-1 w-full rounded border-gray-300 dark:border-gray-700 dark:bg-gray-900 text-sm font-mono"
				/>
			</label>
			<label class="block">
				<span class="lq-text-label">Tags (comma-separated)</span>
				<input
					type="text"
					bind:value={tagsInput}
					placeholder="contracts, nda"
					class="mt-1 w-full rounded border-gray-300 dark:border-gray-700 dark:bg-gray-900 text-sm"
				/>
			</label>
		</div>

		<label class="block">
			<span class="lq-text-label">Body (Markdown system prompt)</span>
			<textarea
				bind:value={body}
				rows="14"
				required
				maxlength="200000"
				placeholder={'You are reviewing NDAs for an in-house legal team.\n\nWalk through:\n1. Parties + scope.\n2. Duration + permitted disclosures.\n...'}
				class="mt-1 w-full rounded border-gray-300 dark:border-gray-700 dark:bg-gray-900 text-sm font-mono"
				data-testid="lq-ai-user-skill-new-body"
			></textarea>
			<p class="lq-text-caption mt-1" style="color: var(--lq-text-tertiary);">
				This text becomes the system-prompt chunk for any chat that attaches the skill. Markdown
				renders verbatim — the model reads it as instructions.
			</p>
		</label>

		<div class="flex items-center justify-end gap-2 pt-2">
			<a
				href="/lq-ai/skills"
				class="lq-btn-secondary lq-text-caption"
			>
				Cancel
			</a>
			<button
				type="submit"
				disabled={!canSubmit}
				class="lq-btn-primary lq-text-caption"
				data-testid="lq-ai-user-skill-new-submit"
			>
				{submitting ? 'Creating…' : 'Create skill'}
			</button>
		</div>
	</form>
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
	.lq-btn-primary:disabled {
		background: var(--lq-text-tertiary);
		cursor: not-allowed;
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
</style>
