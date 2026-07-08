<script lang="ts">
	/**
	 * /lq-ai/admin/branding — deployment white-labeling (BRAND-1b, ADR-F068).
	 *
	 * Single-form admin page over the branding endpoints: product name, one
	 * accent picker per theme (dark auto-suggested from light) fanned out
	 * client-side to the 7-token palette exactly like the first-boot seeder
	 * (see page-helpers), and a raster-only logo (PNG/JPEG/WEBP, ≤512 KB —
	 * the server sniffs magic bytes; SVG is impossible by construction).
	 *
	 * HARD LINE (ADR-F068): the DualBrandingFooter keeps the Apache-2.0 +
	 * LQ.AI attribution — a custom name renders as
	 * "NAME — powered by LQ.AI Oscar Edition", shown in the note below the
	 * name field. Saving refreshes the live shell via refreshBranding().
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	import { brandingApi } from '$lib/lq-ai/api';
	import { LOGO_MAX_BYTES, logoUrl } from '$lib/lq-ai/api/branding';
	import { auth } from '$lib/lq-ai/auth/store';
	import { refreshBranding, sanitizePalette, titleFor } from '$lib/lq-ai/branding/store';

	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import Alert from '$lib/lq-ai/components/primitives/Alert.svelte';
	import FormControl from '$lib/lq-ai/components/primitives/FormControl.svelte';
	import PageShell from '$lib/lq-ai/components/primitives/PageShell.svelte';
	import SectionHeader from '$lib/lq-ai/components/primitives/SectionHeader.svelte';

	import { describeMutationError } from '$lib/lq-ai/admin/page-helpers';
	import {
		DARK_CANVAS,
		DEFAULT_ACCENT_DARK,
		DEFAULT_ACCENT_LIGHT,
		LIGHT_CANVAS,
		accentFromPalette,
		accentWarnings,
		buildPaletteBody,
		suggestDarkAccent,
		validateAccentHex,
		validateProductName
	} from './page-helpers';

	let loading = $state(true);
	let loadError = $state<string | null>(null);

	// ----- Name + accent form -----
	let productName = $state('');
	let accentEnabled = $state(false);
	let accentLight = $state(DEFAULT_ACCENT_LIGHT);
	let accentDark = $state(DEFAULT_ACCENT_DARK);
	/** Once the admin touches the dark picker, stop auto-suggesting. */
	let darkTouched = $state(false);
	let saving = $state(false);
	let saveError = $state<string | null>(null);
	let saveDone = $state(false);

	// ----- Logo -----
	let logoVersion = $state<number | null>(null);
	let logoBusy = $state(false);
	let logoError = $state<string | null>(null);
	let fileInput = $state<HTMLInputElement | null>(null);

	const nameError = $derived(validateProductName(productName));
	const lightHexError = $derived(accentEnabled ? validateAccentHex(accentLight) : null);
	const darkHexError = $derived(accentEnabled ? validateAccentHex(accentDark) : null);
	const lightWarnings = $derived(
		accentEnabled && !lightHexError ? accentWarnings(accentLight, LIGHT_CANVAS) : []
	);
	const darkWarnings = $derived(
		accentEnabled && !darkHexError ? accentWarnings(accentDark, DARK_CANVAS) : []
	);
	const saveBlocked = $derived(!!nameError || !!lightHexError || !!darkHexError);

	async function load() {
		loading = true;
		loadError = null;
		try {
			const resp = await brandingApi.getBranding();
			productName = resp.product_name;
			logoVersion = resp.logo_version;
			const palette = sanitizePalette(resp.palette);
			const hasPalette =
				Object.keys(palette.light).length > 0 || Object.keys(palette.dark).length > 0;
			accentEnabled = hasPalette;
			accentLight = accentFromPalette(palette, 'light', DEFAULT_ACCENT_LIGHT);
			accentDark = accentFromPalette(palette, 'dark', DEFAULT_ACCENT_DARK);
			// A stored palette is an explicit choice — don't overwrite its dark
			// accent with suggestions until the admin edits the light one anew.
			darkTouched = hasPalette;
		} catch (e) {
			loadError = describeMutationError(e, 'Failed to load branding.');
		} finally {
			loading = false;
		}
	}

	function onLightAccentInput(value: string) {
		accentLight = value;
		if (!darkTouched && validateAccentHex(value) === null) {
			accentDark = suggestDarkAccent(value);
		}
	}

	function onDarkAccentInput(value: string) {
		accentDark = value;
		darkTouched = true;
	}

	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (saveBlocked || saving) return;
		saving = true;
		saveError = null;
		saveDone = false;
		try {
			const resp = await brandingApi.updateBranding({
				product_name: productName.trim(),
				palette: buildPaletteBody(accentEnabled, accentLight, accentDark)
			});
			productName = resp.product_name;
			logoVersion = resp.logo_version;
			saveDone = true;
			// Propagate to the live shell (header/footer/titles/style tag/cache).
			await refreshBranding();
		} catch (e) {
			// The API's named 422s (unknown token / bad hex / control chars in
			// the name) surface verbatim.
			saveError = describeMutationError(e, 'Failed to save branding.');
		} finally {
			saving = false;
		}
	}

	async function uploadLogo(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;
		logoError = null;
		if (file.size > LOGO_MAX_BYTES) {
			logoError = `Logo must be ${Math.floor(LOGO_MAX_BYTES / 1024)} KB or smaller.`;
			input.value = '';
			return;
		}
		logoBusy = true;
		try {
			const resp = await brandingApi.uploadLogo(file);
			logoVersion = resp.logo_version;
			await refreshBranding();
		} catch (e) {
			logoError = describeMutationError(e, 'Failed to upload the logo.');
		} finally {
			logoBusy = false;
			input.value = '';
		}
	}

	async function removeLogo() {
		if (logoBusy) return;
		logoBusy = true;
		logoError = null;
		try {
			await brandingApi.deleteLogo();
			logoVersion = null;
			await refreshBranding();
		} catch (e) {
			logoError = describeMutationError(e, 'Failed to remove the logo.');
		} finally {
			logoBusy = false;
		}
	}

	onMount(async () => {
		// Per-page admin guard (Users-page precedent — no admin-layout guard
		// exists; the server's AdminUser dependency gates the writes anyway).
		if (!$auth.user) {
			goto('/lq-ai/login');
			return;
		}
		if (!$auth.user.is_admin) {
			console.warn('non-admin attempted /lq-ai/admin/branding; redirecting');
			goto('/lq-ai');
			return;
		}
		await load();
	});
</script>

<svelte:head>
	<title>{$titleFor('Branding', 'admin')}</title>
</svelte:head>

<PageShell size="wide" data-testid="lq-admin-branding-page">
	<SectionHeader
		title="Branding"
		subtitle="White-label this deployment — product name, accent colours, and logo apply everywhere, including the sign-in page."
	/>

	{#if loadError}
		<div class="mt-6"><Alert intent="error">{loadError}</Alert></div>
	{:else if loading}
		<p class="mt-6 text-sm text-muted-foreground">Loading branding…</p>
	{:else}
		<form class="mt-6 flex max-w-xl flex-col gap-5" novalidate onsubmit={save}>
			<FormControl
				id="lq-branding-name"
				label="Product name"
				optional
				error={nameError}
				help={'Shown in the header, page titles, sign-in page and emails. Leave blank to use "LQ.AI Oscar Edition". The footer keeps the attribution: a custom name renders as "NAME — powered by LQ.AI Oscar Edition".'}
			>
				<Input
					id="lq-branding-name"
					bind:value={productName}
					maxlength={80}
					placeholder="LQ.AI Oscar Edition"
					disabled={saving}
					aria-invalid={!!nameError}
					data-testid="lq-admin-branding-name"
				/>
			</FormControl>

			<label class="flex items-start gap-2 text-sm text-foreground">
				<input
					type="checkbox"
					class="mt-0.5"
					bind:checked={accentEnabled}
					disabled={saving}
					data-testid="lq-admin-branding-accent-enabled"
				/>
				<span>
					<span class="font-medium">Custom accent colour</span>
					<span class="block text-xs text-muted-foreground">
						Recolours links, focus rings, running-state markers and the first chart series
						(one accent per theme, fanned out to the brandable tokens on save). Off = the
						shipped blue. Saving replaces any advanced per-token palette set directly
						through the API.
					</span>
				</span>
			</label>

			{#if accentEnabled}
				<FormControl
					id="lq-branding-accent-light"
					label="Accent — light theme"
					error={lightHexError}
					help="Sits on the white canvas."
				>
					<div class="flex items-center gap-2">
						<input
							type="color"
							class="h-8 w-10 cursor-pointer rounded border border-input bg-transparent p-0.5"
							value={lightHexError ? DEFAULT_ACCENT_LIGHT : accentLight}
							oninput={(e) => onLightAccentInput(e.currentTarget.value)}
							disabled={saving}
							aria-label="Pick the light-theme accent colour"
							data-testid="lq-admin-branding-accent-light-picker"
						/>
						<Input
							id="lq-branding-accent-light"
							class="w-28 font-mono"
							value={accentLight}
							oninput={(e: Event) =>
								onLightAccentInput((e.currentTarget as HTMLInputElement).value)}
							maxlength={7}
							disabled={saving}
							aria-invalid={!!lightHexError}
							data-testid="lq-admin-branding-accent-light"
						/>
					</div>
				</FormControl>
				{#each lightWarnings as warning (warning)}
					<Alert intent="warning">{warning}</Alert>
				{/each}

				<FormControl
					id="lq-branding-accent-dark"
					label="Accent — dark theme"
					error={darkHexError}
					help="Sits on the charcoal canvas. Auto-suggested from the light accent until you edit it."
				>
					<div class="flex items-center gap-2">
						<input
							type="color"
							class="h-8 w-10 cursor-pointer rounded border border-input bg-transparent p-0.5"
							value={darkHexError ? DEFAULT_ACCENT_DARK : accentDark}
							oninput={(e) => onDarkAccentInput(e.currentTarget.value)}
							disabled={saving}
							aria-label="Pick the dark-theme accent colour"
							data-testid="lq-admin-branding-accent-dark-picker"
						/>
						<Input
							id="lq-branding-accent-dark"
							class="w-28 font-mono"
							value={accentDark}
							oninput={(e: Event) =>
								onDarkAccentInput((e.currentTarget as HTMLInputElement).value)}
							maxlength={7}
							disabled={saving}
							aria-invalid={!!darkHexError}
							data-testid="lq-admin-branding-accent-dark"
						/>
					</div>
				</FormControl>
				{#each darkWarnings as warning (warning)}
					<Alert intent="warning">{warning}</Alert>
				{/each}
			{/if}

			{#if saveError}
				<Alert intent="error">{saveError}</Alert>
			{/if}
			{#if saveDone}
				<Alert intent="info">Branding saved.</Alert>
			{/if}

			<div>
				<Button
					type="submit"
					disabled={saving || saveBlocked}
					data-testid="lq-admin-branding-save"
				>
					{saving ? 'Saving…' : 'Save branding'}
				</Button>
			</div>
		</form>

		<section class="mt-10 max-w-xl">
			<h2 class="text-sm font-semibold text-foreground">Logo</h2>
			<p class="mt-1 text-xs text-muted-foreground">
				PNG, JPEG or WEBP, up to {Math.floor(LOGO_MAX_BYTES / 1024)} KB. Shown in the header,
				the sign-in page, and as the favicon. The server verifies the file's magic bytes —
				SVG is not accepted.
			</p>

			{#if logoVersion !== null}
				<div class="mt-3 flex items-center gap-4">
					<img
						src={logoUrl(logoVersion)}
						alt="Current logo"
						class="h-12 w-auto max-w-48 rounded border border-border bg-background object-contain p-1"
						data-testid="lq-admin-branding-logo-preview"
					/>
					<Button
						type="button"
						variant="outline"
						disabled={logoBusy}
						onclick={removeLogo}
						data-testid="lq-admin-branding-logo-delete"
					>
						{logoBusy ? 'Working…' : 'Remove logo'}
					</Button>
				</div>
			{:else}
				<p class="mt-3 text-sm text-muted-foreground">No logo uploaded.</p>
			{/if}

			<div class="mt-3">
				<input
					bind:this={fileInput}
					type="file"
					accept="image/png,image/jpeg,image/webp"
					class="hidden"
					onchange={uploadLogo}
					data-testid="lq-admin-branding-logo-input"
				/>
				<Button
					type="button"
					variant="outline"
					disabled={logoBusy}
					onclick={() => fileInput?.click()}
					data-testid="lq-admin-branding-logo-upload"
				>
					{logoBusy ? 'Uploading…' : logoVersion !== null ? 'Replace logo' : 'Upload logo'}
				</Button>
			</div>

			{#if logoError}
				<div class="mt-3"><Alert intent="error">{logoError}</Alert></div>
			{/if}
		</section>
	{/if}
</PageShell>
