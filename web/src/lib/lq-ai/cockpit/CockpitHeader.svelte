<script lang="ts">
	/**
	 * Cockpit header — brand, ambient trust chrome (ADR-0011 disclosure
	 * stays present), a trust link, theme toggle, settings, sign-out. The
	 * tool surfaces are reached from the rail's Tools section (UX-A): the
	 * legacy header Tools dropdown retired with the `(tools)` shell in UX-A-5.
	 * No AI furniture (ADR-F002): nothing here picks models, skills, or context.
	 */
	import { goto } from '$app/navigation';
	import LogOutIcon from '@lucide/svelte/icons/log-out';
	import MonitorIcon from '@lucide/svelte/icons/monitor';
	import MoonIcon from '@lucide/svelte/icons/moon';
	import PanelLeftIcon from '@lucide/svelte/icons/panel-left';
	import SettingsIcon from '@lucide/svelte/icons/settings';
	import ShieldCheckIcon from '@lucide/svelte/icons/shield-check';
	import SunIcon from '@lucide/svelte/icons/sun';

	import { Button } from '$lib/components/ui/button/index.js';
	import { authApi } from '$lib/lq-ai/api';
	import { logoUrl } from '$lib/lq-ai/api/branding';
	import { clearSession } from '$lib/lq-ai/auth/store';
	import { branding } from '$lib/lq-ai/branding/store';
	import AmbientTrustChrome from '$lib/lq-ai/components/AmbientTrustChrome.svelte';
	import { applyTheme, nextTheme, normalizeTheme, type Theme } from './helpers';

	let {
		railHidden = false,
		onToggleRail
	}: {
		/** Whether the rail is currently collapsed/closed (labels the toggle). */
		railHidden?: boolean;
		onToggleRail?: () => void;
	} = $props();

	let theme: Theme = $state('system');
	$effect(() => {
		theme = normalizeTheme(localStorage.getItem('theme'));
	});

	function cycleTheme() {
		theme = nextTheme(theme);
		applyTheme(theme);
	}

	const THEME_LABEL: Record<Theme, string> = {
		system: 'Theme: follows your system',
		light: 'Theme: light',
		dark: 'Theme: dark'
	};

	async function signOut() {
		try {
			await authApi.logout(); // best-effort server-side revocation
		} catch {
			// Local sign-out proceeds regardless — the refresh token expires
			// server-side on its own.
		}
		clearSession();
		goto('/lq-ai/login');
	}
</script>

<!-- F2-M5: minimal-chrome restyle (already semantic — restyle-only, ADR-F012).
     Quiet muted icon buttons that brighten to `text-foreground` on hover (one
     calm resting state), the trust link + theme/settings/sign-out grouped as
     one tight cluster, single primary accent on the brand. No AI furniture
     (ADR-F002 — the header picks no models/skills/context). Tools moved to the
     rail's Tools section in UX-A. -->
<header
	class="flex h-12 shrink-0 items-center justify-between border-b border-border bg-background px-4"
	data-testid="lq-cockpit-header"
>
	<div class="flex items-center gap-1.5">
		{#if onToggleRail}
			<Button
				variant="ghost"
				size="icon"
				class="text-muted-foreground hover:text-foreground"
				title={railHidden ? 'Show navigation' : 'Hide navigation'}
				aria-label={railHidden ? 'Show navigation' : 'Hide navigation'}
				data-testid="lq-cockpit-rail-toggle"
				onclick={onToggleRail}
			>
				<PanelLeftIcon class="size-4" aria-hidden="true" />
			</Button>
		{/if}
		<!-- BRAND-1b (ADR-F068): a configured custom name replaces the lockup
		     (Svelte {} interpolation only — never {@html}); the default install
		     keeps the LQ.AI Oscar Edition lockup verbatim in the else branch. -->
		{#if $branding.customName}
			<a
				href="/lq-ai"
				class="flex items-center gap-1.5 text-base font-semibold tracking-tight text-foreground no-underline"
			>
				{#if $branding.logoVersion !== null}
					<img
						src={logoUrl($branding.logoVersion)}
						alt=""
						class="h-5 w-auto max-w-24 object-contain"
					/>
				{/if}
				{$branding.productName}
			</a>
		{:else}
			<a href="/lq-ai" class="text-base font-semibold tracking-tight text-foreground no-underline">
				<!-- Real space before the suffix so the anchor's accessible name /
				     copied text reads "LQ.AI Oscar Edition", not "LQ.AIOscar Edition";
				     ml-1 tunes the visual gap on top of the collapsed space. -->
				<span class="text-primary">LQ</span>.AI
				<span class="ml-1 text-xs font-medium tracking-normal text-muted-foreground"
					>Oscar Edition</span
				>
			</a>
		{/if}
	</div>
	<div class="flex items-center gap-1">
		<AmbientTrustChrome />
		<!-- Account / preferences — one tight, quiet icon cluster. Tools live in
		     the rail's Tools section now (UX-A); the header keeps only the
		     transparency link + prefs. -->
		<div class="flex items-center gap-0.5">
			<Button
				variant="ghost"
				size="icon"
				class="text-muted-foreground hover:text-foreground"
				title="Trust &amp; transparency"
				aria-label="Trust &amp; transparency"
				onclick={() => goto('/lq-ai/trust')}
			>
				<ShieldCheckIcon class="size-4" aria-hidden="true" />
			</Button>
			<Button
				variant="ghost"
				size="icon"
				class="text-muted-foreground hover:text-foreground"
				title={THEME_LABEL[theme]}
				aria-label={THEME_LABEL[theme]}
				onclick={cycleTheme}
			>
				{#if theme === 'light'}
					<SunIcon class="size-4" aria-hidden="true" />
				{:else if theme === 'dark'}
					<MoonIcon class="size-4" aria-hidden="true" />
				{:else}
					<MonitorIcon class="size-4" aria-hidden="true" />
				{/if}
			</Button>
			<Button
				variant="ghost"
				size="icon"
				class="text-muted-foreground hover:text-foreground"
				title="Settings"
				aria-label="Settings"
				onclick={() => goto('/lq-ai/settings/appearance')}
			>
				<SettingsIcon class="size-4" aria-hidden="true" />
			</Button>
			<Button
				variant="ghost"
				size="icon"
				class="text-muted-foreground hover:text-foreground"
				title="Sign out"
				aria-label="Sign out"
				onclick={signOut}
			>
				<LogOutIcon class="size-4" aria-hidden="true" />
			</Button>
		</div>
	</div>
</header>
