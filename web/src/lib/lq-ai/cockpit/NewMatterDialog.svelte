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
	import type { PracticeArea } from '$lib/lq-ai/api/practiceAreas';
	import type { Project } from '$lib/lq-ai/types';

	let {
		open = $bindable(false),
		unitLabel,
		practiceAreaId = null,
		areas = [],
		onCreated
	}: {
		open?: boolean;
		unitLabel: string;
		/** F1-S3: file the new matter under this area (null = unfiled). */
		practiceAreaId?: string | null;
		/**
		 * UX-B-5: the configured areas the matter may file under (caller passes
		 * only `configured` ones — ADR-F002: only configured areas are fileable).
		 * When non-empty the dialog shows an explicit area PICKER (defaulting to
		 * the contextual `practiceAreaId`); empty = the legacy bound behaviour.
		 */
		areas?: PracticeArea[];
		onCreated: (project: Project) => void;
	} = $props();

	// The area the matter will file under: the user's pick when a picker is
	// shown, else the bound `practiceAreaId`. The dialog's noun/title follow the
	// CHOSEN area's unit label (Matter / Programme / Deal), falling back to the
	// `unitLabel` prop when no area resolves.
	let name = $state('');
	let creating = $state(false);
	let error = $state<string | null>(null);
	let selectedAreaId = $state<string | null>(null);

	const selectedArea = $derived(
		selectedAreaId === null ? null : (areas.find((a) => a.id === selectedAreaId) ?? null)
	);
	const effectiveUnitLabel = $derived(selectedArea?.unit_label ?? unitLabel);
	const noun = $derived(effectiveUnitLabel.toLowerCase());

	// A reopened dialog starts clean — no stale error/draft from last time —
	// and the picker defaults to the contextual area (or the first configured
	// area when there's no context), so the binding is explicit, never silent.
	$effect(() => {
		if (open) {
			name = '';
			error = null;
			const ctx =
				practiceAreaId && areas.some((a) => a.id === practiceAreaId) ? practiceAreaId : null;
			selectedAreaId = ctx ?? (areas.length > 0 ? areas[0].id : practiceAreaId);
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
			error = result.nameError.replace('Matter', effectiveUnitLabel);
			return;
		}
		const trimmed = name.trim();
		creating = true;
		error = null;
		try {
			const project = await projectsApi.createProject({
				name: trimmed,
				...(selectedAreaId ? { practice_area_id: selectedAreaId } : {})
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
			{#if areas.length > 0}
				<!-- UX-B-5: explicit area selection at matter creation — only
				     configured areas are fileable (ADR-F002); the binding drives
				     the whole agent identity server-side (composition.py). -->
				<label
					class="mb-1.5 block text-xs font-medium text-muted-foreground"
					for="lq-cockpit-new-matter-area"
				>
					Practice area
				</label>
				<select
					id="lq-cockpit-new-matter-area"
					bind:value={selectedAreaId}
					class="mb-3 h-9 w-full rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30"
					data-testid="lq-cockpit-new-matter-area"
				>
					{#each areas as a (a.id)}
						<option value={a.id}>{a.name}</option>
					{/each}
				</select>
			{/if}
			<Input
				bind:value={name}
				placeholder="e.g. Acme MSA renewal"
				maxlength={200}
				aria-label="{effectiveUnitLabel} name"
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
