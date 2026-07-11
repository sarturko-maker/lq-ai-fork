<script lang="ts">
	/**
	 * /lq-ai/admin/setup — the guided setup wizard (B-7b, ADR-F067 D4).
	 *
	 * A thin multi-step UI over the shipped profiles endpoints (B-7a): pick a
	 * profile → (name the area, blank only) → House Brief → review & activate →
	 * done. The single mutation is `profilesApi.applyProfile`, one atomic
	 * transaction that adopts the profile's Library entries AND binds them — the
	 * fix for the G13 fresh-org cliff (a fresh org's seeded bindings are inert
	 * until something is adopted, so the agent ships bare).
	 *
	 * Admin-gated AND operator-fenced client-side: `apply` 403s the platform
	 * operator server-side (ADR-F064), and `is_admin` admits the operator
	 * elsewhere, so a plain `is_admin` guard would walk them into a 403 — we
	 * branch on `role` and redirect the operator out. The server `AdminUser`
	 * dependency + operator fence remain the real enforcement.
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	import { titleFor } from '$lib/lq-ai/branding/store';
	import { organizationProfileApi, profilesApi } from '$lib/lq-ai/api';
	import { auth } from '$lib/lq-ai/auth/store';
	import type { ProfileApplyResult, ProfileDetail, ProfileSummary } from '$lib/lq-ai/api/profiles';
	import { renderModelMarkdown } from '$lib/lq-ai/sanitize-markdown';

	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import Alert from '$lib/lq-ai/components/primitives/Alert.svelte';
	import Card from '$lib/lq-ai/components/primitives/Card.svelte';
	import CardGrid from '$lib/lq-ai/components/primitives/CardGrid.svelte';
	import FormControl from '$lib/lq-ai/components/primitives/FormControl.svelte';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';
	import StepRail from '$lib/lq-ai/components/primitives/StepRail.svelte';

	import { describeMutationError } from '$lib/lq-ai/admin/page-helpers';
	import {
		SETUP_DISMISSED_KEY,
		UNIT_LABELS,
		buildApplyBody,
		canProceed,
		describeApplyOutcome,
		isValidSlug,
		rosterNames,
		wizardSteps,
		type BlankIdentity,
		type WizardStepKey
	} from './page-helpers';

	// ----- load state -----
	let loading = $state(true);
	let loadError = $state<string | null>(null);
	let profiles = $state<ProfileSummary[]>([]);

	// ----- wizard state -----
	let stepIndex = $state(0);
	let selectedProfile = $state<ProfileSummary | null>(null);
	let detail = $state<ProfileDetail | null>(null);
	let detailLoading = $state(false);
	let detailError = $state<string | null>(null);
	// Monotonic guard so an out-of-order profile-detail fetch (fast re-click on the
	// picker) can't leave `detail` describing a different profile than `selectedProfile`.
	let detailToken = 0;
	let identity = $state<BlankIdentity>({ targetKey: '', name: '', unitLabel: 'Matter' });

	// ----- House Brief step (reuses the B-1 organization-profile surface) -----
	let brief = $state('');
	let briefSaving = $state(false);
	let briefError = $state<string | null>(null);
	let briefSaved = $state(false);

	// ----- apply -----
	let applying = $state(false);
	let applyError = $state<string | null>(null);
	let applyResult = $state<ProfileApplyResult | null>(null);

	const steps = $derived(wizardSteps(selectedProfile?.kind ?? null));
	const currentStep = $derived((steps[stepIndex]?.key ?? 'profile') as WizardStepKey);
	const gateOk = $derived(canProceed(currentStep, { selectedProfile, identity }));
	const roster = $derived(detail ? rosterNames(detail.agent_config) : []);
	const hitlTools = $derived(detail ? Object.keys(detail.hitl).filter((k) => detail!.hitl[k]) : []);
	const keyError = $derived(
		identity.targetKey.trim() === '' || isValidSlug(identity.targetKey.trim())
			? null
			: 'Use lowercase letters, digits and hyphens (e.g. “disputes”).'
	);
	// The receipt names the AREA. For a blank profile that's the admin-entered
	// name (the profile's own display_name is the generic "Blank"); for an area
	// profile it's the profile's display name.
	const outcomeName = $derived(
		selectedProfile?.kind === 'blank'
			? identity.name.trim() || identity.targetKey.trim()
			: (selectedProfile?.display_name ?? 'Your area')
	);
	const outcome = $derived(applyResult ? describeApplyOutcome(applyResult, outcomeName) : null);

	async function load() {
		loading = true;
		loadError = null;
		try {
			const [list, org] = await Promise.all([
				profilesApi.listProfiles(),
				organizationProfileApi.getOrganizationProfile()
			]);
			profiles = list.profiles;
			brief = org.content_md;
		} catch (e) {
			loadError = describeMutationError(e, 'Failed to load the setup wizard.');
		} finally {
			loading = false;
		}
	}

	async function selectProfile(p: ProfileSummary) {
		selectedProfile = p;
		applyResult = null;
		applyError = null;
		if (p.kind === 'blank') {
			identity = { targetKey: '', name: '', unitLabel: 'Matter' };
		}
		// Fetch the full manifest so the review step is ready when reached. Guard
		// with a token so a stale (out-of-order) response can't overwrite a newer
		// selection's detail — else review/activate could describe the wrong profile.
		detail = null;
		detailError = null;
		detailLoading = true;
		const token = ++detailToken;
		try {
			const d = await profilesApi.getProfile(p.name);
			if (token !== detailToken) return; // superseded by a newer selectProfile
			detail = d;
		} catch (e) {
			if (token !== detailToken) return;
			detailError = describeMutationError(e, 'Failed to load this profile.');
		} finally {
			if (token === detailToken) detailLoading = false;
		}
	}

	function next() {
		if (!gateOk) return;
		if (stepIndex < steps.length - 1) stepIndex += 1;
	}

	function back() {
		if (stepIndex > 0) stepIndex -= 1;
	}

	function goToStep(i: number) {
		// StepRail only fires for COMPLETED steps (< current), so this is back-nav.
		if (i >= 0 && i < stepIndex) stepIndex = i;
	}

	async function saveBrief() {
		if (briefSaving) return;
		briefSaving = true;
		briefError = null;
		briefSaved = false;
		try {
			const resp = await organizationProfileApi.updateOrganizationProfile({ content_md: brief });
			brief = resp.content_md;
			briefSaved = true;
		} catch (e) {
			briefError = describeMutationError(e, 'Failed to save the House Brief.');
		} finally {
			briefSaving = false;
		}
	}

	async function apply() {
		if (!selectedProfile || applying) return;
		applying = true;
		applyError = null;
		try {
			const body = buildApplyBody(selectedProfile.kind, identity);
			applyResult = await profilesApi.applyProfile(selectedProfile.name, body);
			// Completing setup stops the cockpit landing from auto-launching again.
			try {
				localStorage.setItem(SETUP_DISMISSED_KEY, '1');
			} catch {
				// private-mode / storage-disabled — non-fatal, the wizard still completed.
			}
			stepIndex = steps.length - 1; // → done
		} catch (e) {
			applyError = describeMutationError(e, 'Could not activate this profile. Please try again.');
		} finally {
			applying = false;
		}
	}

	function skipForNow() {
		try {
			localStorage.setItem(SETUP_DISMISSED_KEY, '1');
		} catch {
			// non-fatal
		}
		goto('/lq-ai');
	}

	onMount(async () => {
		if (!$auth.user) {
			goto('/lq-ai/login');
			return;
		}
		// Operator-fenced (ADR-F064): apply 403s the operator, and is_admin admits
		// the operator, so branch on role and redirect them out rather than let
		// them walk into a 403.
		if (!$auth.user.is_admin || $auth.user.role === 'operator') {
			console.warn('non-tenant-admin attempted /lq-ai/admin/setup; redirecting');
			goto('/lq-ai');
			return;
		}
		await load();
	});
</script>

<svelte:head>
	<title>{$titleFor('Set up', 'admin')}</title>
</svelte:head>

<PageShell size="wide" data-testid="lq-admin-setup-page">
	<div class="flex items-start justify-between gap-4">
		<SectionHeader
			title="Set up a practice area"
			subtitle="Turn on a ready-made practice area — its playbook, tools and sub-agents — so its agent works from the first matter. You can change everything later."
		/>
		{#if currentStep !== 'done'}
			<Button
				type="button"
				variant="ghost"
				size="sm"
				onclick={skipForNow}
				data-testid="lq-setup-skip"
			>
				Skip for now
			</Button>
		{/if}
	</div>

	{#if loadError}
		<div class="mt-6"><Alert intent="error">{loadError}</Alert></div>
	{:else if loading}
		<p class="mt-6 text-sm text-muted-foreground">Loading…</p>
	{:else}
		<div class="mt-6 max-w-3xl">
			<StepRail {steps} current={stepIndex} onselect={goToStep} />
		</div>

		<div class="mt-8 max-w-3xl" data-testid={`lq-setup-step-${currentStep}`}>
			{#if currentStep === 'profile'}
				<!-- ───────── Step: choose a profile ───────── -->
				<SectionHeader
					size="section"
					title="Choose a starting point"
					subtitle="Each profile brings a practice area to life with its doctrine, skills, tools and sub-agents. Start blank to build your own."
				/>
				<div class="mt-4">
					<CardGrid cols={3}>
						{#each profiles as p (p.name)}
							{@const selected = selectedProfile?.name === p.name}
							<Card
								interactive
								bordered
								pad="compact"
								aria-pressed={selected}
								onclick={() => selectProfile(p)}
								data-testid={`lq-setup-profile-${p.name}`}
								class={selected ? 'ring-2 ring-brand' : ''}
							>
								<div class="flex min-h-full flex-col gap-2">
									<div class="flex items-center justify-between gap-2">
										<p class="text-sm font-semibold text-foreground">{p.display_name}</p>
										<span
											class="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground"
										>
											{p.kind === 'blank' ? 'Blank' : 'Ready-made'}
										</span>
									</div>
									{#if p.description}
										<p class="text-xs text-muted-foreground">{p.description}</p>
									{/if}
									<p class="mt-auto pt-1 text-[11px] text-muted-foreground">
										{#if p.kind === 'blank'}
											Start from scratch
										{:else}
											{p.skill_count} skills · {p.tool_group_count} tools · {p.subagent_count} sub-agents
										{/if}
									</p>
								</div>
							</Card>
						{/each}
					</CardGrid>
				</div>
			{:else if currentStep === 'name'}
				<!-- ───────── Step: name the area (blank only) ───────── -->
				<SectionHeader
					size="section"
					title="Name your practice area"
					subtitle="A blank area starts with no capabilities — you'll add them afterward from the Store."
				/>
				<div class="mt-4 flex flex-col gap-4">
					<FormControl
						id="lq-setup-key"
						label="Key"
						required
						error={keyError}
						help="A short, stable identifier used in links — lowercase letters, digits and hyphens."
					>
						<Input
							id="lq-setup-key"
							bind:value={identity.targetKey}
							placeholder="disputes"
							required
							aria-invalid={!!keyError}
							aria-describedby={keyError ? 'lq-setup-key-error' : undefined}
							data-testid="lq-setup-key-input"
						/>
					</FormControl>
					<FormControl id="lq-setup-name" label="Display name" required>
						<Input
							id="lq-setup-name"
							bind:value={identity.name}
							placeholder="Disputes"
							data-testid="lq-setup-name-input"
						/>
					</FormControl>
					<FormControl
						id="lq-setup-unit"
						label="Unit of work"
						required
						help="What one piece of work is called in this area."
					>
						<select
							id="lq-setup-unit"
							bind:value={identity.unitLabel}
							class="h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
							data-testid="lq-setup-unit-select"
						>
							{#each UNIT_LABELS as u (u)}
								<option value={u}>{u}</option>
							{/each}
						</select>
					</FormControl>
				</div>
			{:else if currentStep === 'brief'}
				<!-- ───────── Step: House Brief ───────── -->
				<SectionHeader
					size="section"
					title="House Brief (optional)"
					subtitle="Who the company is and who its legal team acts for — injected read-only into every agent run, in every practice area. You can set this now or later."
				/>
				<div class="mt-4 flex flex-col gap-3">
					<FormControl
						id="lq-setup-brief"
						label="House Brief"
						optional
						help="Markdown supported. Worth including: the company and what it does, its group structure, the risk posture to take with counterparties, and any house conventions."
					>
						<Textarea
							id="lq-setup-brief"
							bind:value={brief}
							rows={10}
							class="font-mono text-sm"
							disabled={briefSaving}
							data-testid="lq-setup-brief-textarea"
						/>
					</FormControl>
					{#if briefError}
						<Alert intent="error">{briefError}</Alert>
					{/if}
					{#if briefSaved}
						<Alert intent="info">House Brief saved.</Alert>
					{/if}
					<div>
						<Button
							type="button"
							variant="outline"
							size="sm"
							disabled={briefSaving}
							onclick={saveBrief}
							data-testid="lq-setup-brief-save"
						>
							{briefSaving ? 'Saving…' : 'Save House Brief'}
						</Button>
					</div>
					<p class="text-xs text-muted-foreground">
						Optional — you can refine it any time on the
						<a href="/lq-ai/admin/house-brief" class="underline">House Brief page</a>.
					</p>
				</div>
			{:else if currentStep === 'review'}
				<!-- ───────── Step: review & activate ───────── -->
				<SectionHeader
					size="section"
					title="Review & activate"
					subtitle="Activating adopts everything below into your Library and binds it to the area — in one step. Nothing reaches the agent until you do this."
				/>
				{#if detailError}
					<div class="mt-4"><Alert intent="error">{detailError}</Alert></div>
				{:else if detailLoading || !detail}
					<p class="mt-4 text-sm text-muted-foreground">Loading the profile…</p>
				{:else}
					<div class="mt-4 flex flex-col gap-5">
						{#if selectedProfile?.kind === 'blank'}
							<Card bordered pad="compact">
								<p class="text-sm font-semibold text-foreground">
									New area: {identity.name || identity.targetKey}
								</p>
								<p class="mt-1 text-xs text-muted-foreground">
									Key <code>{identity.targetKey}</code> · unit “{identity.unitLabel}”. A blank area
									starts empty — add capabilities from the
									<a href="/lq-ai/admin/store" class="underline">Store</a> once it's created.
								</p>
							</Card>
						{:else}
							<Card bordered pad="compact" data-testid="lq-setup-activation-summary">
								<p class="text-sm text-foreground">
									Activating <strong>{selectedProfile?.display_name}</strong> will adopt
									<strong>{detail.skills.length}</strong>
									{detail.skills.length === 1 ? 'skill' : 'skills'} and
									<strong>{detail.tool_groups.length}</strong>
									{detail.tool_groups.length === 1 ? 'tool group' : 'tool groups'} into your Library,
									bind them to the area{#if roster.length}, and set a
										<strong>{roster.length}</strong>-sub-agent roster{/if}.
								</p>
							</Card>

							{#if detail.skills.length}
								<section aria-label="Skills">
									<p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
										Skills
									</p>
									<div class="mt-2 flex flex-wrap gap-1.5">
										{#each detail.skills as s (s)}
											<span
												class="rounded-full border border-border px-2 py-0.5 text-xs text-foreground"
											>
												{s}
											</span>
										{/each}
									</div>
								</section>
							{/if}

							{#if detail.tool_groups.length}
								<section aria-label="Tool groups">
									<p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
										Tools
									</p>
									<div class="mt-2 flex flex-wrap gap-1.5">
										{#each detail.tool_groups as t (t)}
											<span
												class="rounded-full border border-border px-2 py-0.5 text-xs text-foreground"
											>
												{t}
											</span>
										{/each}
									</div>
								</section>
							{/if}

							{#if roster.length}
								<section aria-label="Sub-agents">
									<p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
										Sub-agents
									</p>
									<div class="mt-2 flex flex-wrap gap-1.5">
										{#each roster as r (r)}
											<span
												class="rounded-full border border-border px-2 py-0.5 text-xs text-foreground"
											>
												{r}
											</span>
										{/each}
									</div>
								</section>
							{/if}

							{#if hitlTools.length}
								<section aria-label="Stop-and-ask">
									<p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
										Stop-and-ask
									</p>
									<div class="mt-2 flex flex-wrap gap-1.5">
										{#each hitlTools as h (h)}
											<span
												class="rounded-full border border-border px-2 py-0.5 text-xs text-foreground"
											>
												{h}
											</span>
										{/each}
									</div>
								</section>
							{/if}

							{#if detail.doctrine}
								<details class="rounded-lg border border-border bg-card p-3">
									<summary class="cursor-pointer text-sm font-medium text-foreground">
										View the area's doctrine
									</summary>
									<div
										class="prose prose-sm dark:prose-invert mt-3 max-h-64 max-w-none overflow-y-auto"
										data-testid="lq-setup-doctrine"
									>
										<!-- eslint-disable-next-line svelte/no-at-html-tags — renderModelMarkdown-sanitized -->
										{@html renderModelMarkdown(detail.doctrine)}
									</div>
								</details>
							{/if}
						{/if}

						{#if applyError}
							<Alert intent="error">{applyError}</Alert>
						{/if}
					</div>
				{/if}
			{:else if currentStep === 'done'}
				<!-- ───────── Step: done / receipt ───────── -->
				{#if outcome}
					<div class="flex flex-col gap-4" data-testid="lq-setup-receipt">
						<Alert intent="info">
							<p class="font-medium">{outcome.headline}</p>
							{#each outcome.lines as line (line)}
								<p class="mt-1">{line}</p>
							{/each}
						</Alert>
						<div class="flex flex-wrap gap-2">
							<Button type="button" onclick={() => goto('/lq-ai')} data-testid="lq-setup-try-now">
								Try it now
							</Button>
							<Button type="button" variant="outline" onclick={() => goto('/lq-ai/admin/users')}>
								Invite a colleague
							</Button>
							<Button type="button" variant="outline" onclick={() => goto('/lq-ai/admin/areas')}>
								Practice areas
							</Button>
						</div>
						<p class="text-xs text-muted-foreground">
							Fine-tune capabilities any time on the
							<a href="/lq-ai/admin/store" class="underline">Store</a> and
							<a href="/lq-ai/admin/library" class="underline">Library</a> pages.
						</p>
					</div>
				{/if}
			{/if}
		</div>

		<!-- ───────── footer nav ───────── -->
		{#if currentStep !== 'done'}
			<div class="mt-8 flex max-w-3xl items-center justify-between gap-3">
				<Button
					type="button"
					variant="ghost"
					disabled={stepIndex === 0}
					onclick={back}
					data-testid="lq-setup-back"
				>
					Back
				</Button>
				{#if currentStep === 'review'}
					<Button
						type="button"
						disabled={applying || detailLoading || !detail}
						onclick={apply}
						data-testid="lq-setup-activate"
					>
						{#if applying}
							Activating…
						{:else if selectedProfile?.kind === 'blank'}
							Create area
						{:else}
							Activate {selectedProfile?.display_name}
						{/if}
					</Button>
				{:else}
					<Button type="button" disabled={!gateOk} onclick={next} data-testid="lq-setup-next">
						Next
					</Button>
				{/if}
			</div>
		{/if}
	{/if}
</PageShell>
