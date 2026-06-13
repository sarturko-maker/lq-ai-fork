<script lang="ts">
	import { projectsApi } from '$lib/lq-ai/api';
	import type { Project } from '$lib/lq-ai/types';
	import { validateNewMatter, type TierFloor } from '$lib/lq-ai/validators/matter';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import ModalShell from './primitives/ModalShell.svelte';
	import FormControl from './primitives/FormControl.svelte';
	import Alert from './primitives/Alert.svelte';
	import InfoTip from './InfoTip.svelte';

	let {
		onClose,
		onCreated
	}: {
		onClose: () => void;
		/**
		 * The CALLER owns post-create navigation (F0-S8): the Matters page routes
		 * to the new matter's detail; the Agents tab binds the matter in place — a
		 * hardcoded goto here would yank the user out of the conversation.
		 */
		onCreated: (matter: Project) => void;
	} = $props();

	// Mounted == open; the dialog drives close (Escape / overlay / X / Cancel),
	// and we propagate that to the caller so it unmounts us.
	let open = $state(true);
	$effect(() => {
		if (!open) onClose();
	});

	// Form state
	let name = $state('');
	let description = $state('');
	let privileged = $state(false);
	let tierFloor = $state<TierFloor | null>(null);

	// UI state
	let submitting = $state(false);
	let nameError = $state<string | null>(null);
	let tierError = $state<string | null>(null);
	let submitError = $state<string | null>(null);

	// A non-privileged matter never carries a tier floor.
	$effect(() => {
		if (!privileged) tierFloor = null;
	});

	async function handleSubmit(event: SubmitEvent) {
		event.preventDefault();
		nameError = null;
		tierError = null;
		submitError = null;

		const result = validateNewMatter({
			name,
			description,
			privileged,
			minimum_inference_tier: tierFloor
		});
		nameError = result.nameError;
		tierError = result.tierError;
		if (!result.valid) return;

		submitting = true;
		try {
			const created = await projectsApi.createProject({
				name: name.trim(),
				description: description.trim() || undefined,
				privileged,
				minimum_inference_tier: tierFloor ?? undefined
			});
			onCreated(created);
		} catch (e: unknown) {
			submitError =
				e instanceof Error
					? (e.message ?? "Couldn't reach the server. Try again.")
					: "Couldn't reach the server. Try again.";
		} finally {
			submitting = false;
		}
	}

	// Under PRD §1.5.2, lower tier number = stronger security.
	// "Tier N or stronger" means the floor is N; tiers 1..N are all allowed.
	const TIER_OPTIONS: { value: TierFloor; label: string }[] = [
		{ value: 1, label: 'Tier 1 only' },
		{ value: 2, label: 'Tier 2 or stronger' },
		{ value: 3, label: 'Tier 3 or stronger' },
		{ value: 4, label: 'Tier 4 or stronger' },
		{ value: 5, label: 'Tier 5 or stronger (any tier)' }
	];
</script>

<ModalShell bind:open title="New matter" contentClass="sm:max-w-lg">
	<form id="nmm-form" class="flex flex-col gap-4" novalidate onsubmit={handleSubmit}>
		<FormControl id="nmm-name" label="Matter name" required error={nameError}>
			<Input
				id="nmm-name"
				type="text"
				bind:value={name}
				placeholder="e.g. Acme NDA Review"
				maxlength={200}
				required
				disabled={submitting}
				aria-invalid={!!nameError}
				aria-describedby={nameError ? 'nmm-name-error' : undefined}
			/>
		</FormControl>

		<FormControl id="nmm-description" label="Description" optional>
			<Textarea
				id="nmm-description"
				bind:value={description}
				rows={4}
				maxlength={2000}
				placeholder="Brief description of this matter…"
				disabled={submitting}
			/>
		</FormControl>

		<div class="flex items-center gap-2">
			<input
				id="nmm-privileged"
				type="checkbox"
				class="size-4 accent-primary"
				bind:checked={privileged}
				disabled={submitting}
			/>
			<label class="cursor-pointer text-[13px] font-medium text-foreground" for="nmm-privileged">
				Attorney-client privileged
			</label>
			<InfoTip
				content="Marks this matter as covered by attorney-client privilege. Requires you to set a minimum inference tier floor (below) so privileged content can't route to weaker providers. Tags every chat and audit-log entry as privileged for e-discovery filtering. Recommended for client work."
			/>
		</div>

		{#if privileged}
			<FormControl id="nmm-tier" label="Minimum inference tier" required error={tierError}>
				<select
					id="nmm-tier"
					class="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30"
					bind:value={tierFloor}
					disabled={submitting}
					aria-invalid={!!tierError}
					aria-describedby={tierError ? 'nmm-tier-error' : undefined}
				>
					<option value={null}>(none)</option>
					{#each TIER_OPTIONS as opt (opt.value)}
						<option value={opt.value}>{opt.label}</option>
					{/each}
				</select>
			</FormControl>
		{/if}

		{#if submitError}
			<Alert intent="error">{submitError}</Alert>
		{/if}
	</form>

	{#snippet footer()}
		<Button type="button" variant="outline" disabled={submitting} onclick={() => (open = false)}>
			Cancel
		</Button>
		<Button type="submit" form="nmm-form" disabled={submitting}>
			{submitting ? 'Creating matter…' : 'Create matter'}
		</Button>
	{/snippet}
</ModalShell>
