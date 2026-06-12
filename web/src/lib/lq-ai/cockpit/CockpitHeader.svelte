<script lang="ts">
	/**
	 * Cockpit header — brand, ambient trust chrome (ADR-0011 disclosure
	 * stays present), a Tools menu linking to the legacy tool surfaces
	 * (they keep working unchanged until F3 demotes them), theme toggle,
	 * settings. No AI furniture (ADR-F002): nothing here picks models,
	 * skills, or context.
	 */
	import { goto } from '$app/navigation';
	import LogOutIcon from '@lucide/svelte/icons/log-out';
	import MonitorIcon from '@lucide/svelte/icons/monitor';
	import MoonIcon from '@lucide/svelte/icons/moon';
	import SettingsIcon from '@lucide/svelte/icons/settings';
	import ShieldCheckIcon from '@lucide/svelte/icons/shield-check';
	import SunIcon from '@lucide/svelte/icons/sun';
	import WrenchIcon from '@lucide/svelte/icons/wrench';

	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { authApi } from '$lib/lq-ai/api';
	import { clearSession } from '$lib/lq-ai/auth/store';
	import AmbientTrustChrome from '$lib/lq-ai/components/AmbientTrustChrome.svelte';
	import { visibleTabsFor } from '$lib/lq-ai/components/TopTabBar.svelte';
	import type { User } from '$lib/lq-ai/tabs';
	import { preferences } from '$lib/lq-ai/stores/preferences';
	import { applyTheme, nextTheme, normalizeTheme, type Theme } from './helpers';

	let { user }: { user: User | null } = $props();

	const toolTabs = $derived(
		visibleTabsFor(user, { autonomousEnabled: $preferences.autonomous_enabled }).filter(
			(t) => t.id !== 'home'
		)
	);

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

<header
	class="flex h-12 shrink-0 items-center justify-between border-b border-border bg-background px-4"
>
	<a href="/lq-ai" class="text-base font-semibold tracking-tight text-foreground no-underline">
		<span class="text-primary">LQ</span>.AI
	</a>
	<div class="flex items-center gap-1.5">
		<AmbientTrustChrome />
		<DropdownMenu.Root>
			<DropdownMenu.Trigger>
				{#snippet child({ props })}
					<Button {...props} variant="ghost" size="sm" class="gap-1.5 text-muted-foreground">
						<WrenchIcon class="size-4" aria-hidden="true" />
						Tools
					</Button>
				{/snippet}
			</DropdownMenu.Trigger>
			<DropdownMenu.Content align="end" class="w-52">
				<DropdownMenu.Label>Tool surfaces</DropdownMenu.Label>
				{#each toolTabs as tab (tab.id)}
					<DropdownMenu.Item onSelect={() => goto(tab.route)}>
						<span aria-hidden="true">{tab.icon}</span>
						{tab.label}
					</DropdownMenu.Item>
				{/each}
				<DropdownMenu.Separator />
				<!-- Transparency stays reachable from the landing chrome
				     (PRD §1.3; the retired dashboard held the trust page link). -->
				<DropdownMenu.Item onSelect={() => goto('/lq-ai/trust')}>
					<ShieldCheckIcon class="size-4" aria-hidden="true" />
					Trust &amp; transparency
				</DropdownMenu.Item>
			</DropdownMenu.Content>
		</DropdownMenu.Root>
		<Button
			variant="ghost"
			size="icon"
			class="text-muted-foreground"
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
			class="text-muted-foreground"
			title="Settings"
			aria-label="Settings"
			onclick={() => goto('/lq-ai/settings/appearance')}
		>
			<SettingsIcon class="size-4" aria-hidden="true" />
		</Button>
		<Button
			variant="ghost"
			size="icon"
			class="text-muted-foreground"
			title="Sign out"
			aria-label="Sign out"
			onclick={signOut}
		>
			<LogOutIcon class="size-4" aria-hidden="true" />
		</Button>
	</div>
</header>
