<!--
	AppShell — the sidebar + main layout skeleton (F2-VL1, ADR-F013 §6/§7).

	The Vercel layout: a 264px `--sidebar` rail (brand · New matter · recent
	matters · account footer — all caller-supplied via the `sidebar` snippet)
	beside a main column with an optional thin top bar (breadcrumb + actions)
	above the scrollable content. This primitive owns ONLY the chrome skeleton +
	tokens; the rail's contents are composed from the other primitives by the
	consumer (the `_vl-lab` proof now; the real cockpit in VL2).

	Responsive: the rail collapses (hidden) below `lg`, leaving the main column
	full-width — VL2 wires the existing AreaRail drawer/toggle for narrow. The
	shell fills its parent (`h-full`); the consuming route owns the 100vh box.
	Presentation only; semantic tokens only — no new token scale.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { HTMLAttributes } from 'svelte/elements';

	let {
		sidebar,
		topbar = undefined,
		class: klass = '',
		children,
		...rest
	}: {
		sidebar: Snippet;
		topbar?: Snippet;
		children: Snippet;
	} & HTMLAttributes<HTMLDivElement> = $props();
</script>

<div class="grid h-full min-h-0 lg:grid-cols-[264px_minmax(0,1fr)] {klass}" {...rest}>
	<aside
		class="bg-sidebar text-sidebar-foreground border-border hidden min-h-0 flex-col overflow-y-auto border-r lg:flex"
	>
		{@render sidebar()}
	</aside>
	<div class="flex min-h-0 min-w-0 flex-col">
		{#if topbar}
			<div class="border-border flex h-14 shrink-0 items-center justify-between border-b px-7">
				{@render topbar()}
			</div>
		{/if}
		<main class="min-h-0 min-w-0 flex-1 overflow-y-auto">
			{@render children()}
		</main>
	</div>
</div>
