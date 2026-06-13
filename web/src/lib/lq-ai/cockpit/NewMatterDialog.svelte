<script lang="ts">
	/**
	 * Quick pick-or-create dialog (S8 plumbing: POST /projects, slug
	 * auto-derived server-side). Name only — privileged status, tier
	 * floors, and documents are managed in the Matters tool; quick-create
	 * never silently sets a privilege posture.
	 */
	import * as Dialog from '$lib/components/ui/dialog/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { projectsApi } from '$lib/lq-ai/api';
	import { LQAIApiError } from '$lib/lq-ai/api/client';
	import { validateNewMatter } from '$lib/lq-ai/validators/matter';
	import type { Project } from '$lib/lq-ai/types';

	let {
		open = $bindable(false),
		unitLabel,
		practiceAreaId = null,
		onCreated
	}: {
		open?: boolean;
		unitLabel: string;
		/** F1-S3: file the new matter under this area (null = unfiled). */
		practiceAreaId?: string | null;
		onCreated: (project: Project) => void;
	} = $props();

	const noun = $derived(unitLabel.toLowerCase());

	let name = $state('');
	let creating = $state(false);
	let error = $state<string | null>(null);

	// A reopened dialog starts clean — no stale error/draft from last time.
	$effect(() => {
		if (open) {
			name = '';
			error = null;
		}
	});

	async function create(event: SubmitEvent) {
		event.preventDefault();
		// Same name rules as the Matters-page modal (shared validator —
		// quick-create never sets privileged, so tier rules can't fire);
		// only the noun is re-worded per the area's unit label.
		const result = validateNewMatter({
			name,
			description: '',
			privileged: false,
			minimum_inference_tier: null
		});
		if (result.nameError) {
			error = result.nameError.replace('Matter', unitLabel);
			return;
		}
		const trimmed = name.trim();
		creating = true;
		error = null;
		try {
			const project = await projectsApi.createProject({
				name: trimmed,
				...(practiceAreaId ? { practice_area_id: practiceAreaId } : {})
			});
			open = false;
			name = '';
			onCreated(project);
		} catch (e: unknown) {
			error = e instanceof LQAIApiError ? e.message : 'Could not create — try again.';
		} finally {
			creating = false;
		}
	}
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="shadow-lg sm:max-w-md">
		<Dialog.Header>
			<Dialog.Title>New {noun}</Dialog.Title>
			<Dialog.Description>
				Names are visible across the workspace. Privileged status, tier floors, and documents are
				managed in the Matters tool.
			</Dialog.Description>
		</Dialog.Header>
		<form onsubmit={create}>
			<Input
				bind:value={name}
				placeholder="e.g. Acme MSA renewal"
				maxlength={200}
				aria-label="{unitLabel} name"
				data-testid="lq-cockpit-new-matter-name"
			/>
			{#if error}
				<p class="mt-2 text-sm text-destructive">{error}</p>
			{/if}
			<Dialog.Footer class="mt-4">
				<Button type="button" variant="outline" onclick={() => (open = false)}>Cancel</Button>
				<Button type="submit" disabled={creating} data-testid="lq-cockpit-new-matter-create">
					{creating ? 'Creating…' : `Create ${noun}`}
				</Button>
			</Dialog.Footer>
		</form>
	</Dialog.Content>
</Dialog.Root>
