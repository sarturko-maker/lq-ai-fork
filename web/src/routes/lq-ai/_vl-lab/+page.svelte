<script lang="ts">
	/**
	 * `/lq-ai/_vl-lab` — internal F013 design-language scratch surface (VL1,
	 * ADR-F013). Same contract as `_ae-lab`: unadvertised + auth-gated + linked
	 * from nowhere, so it changes NO live surface. The web container always
	 * serves a prod build, so "dev-only" is an internal leading-`_` route (not
	 * an `import.meta.env.DEV` compile-out) — which keeps it Cypress-testable on
	 * :3000 and proves the VL1 primitives render in the real bundle on the VL0
	 * tokens.
	 *
	 * Two parts: (1) the `direction-vercel` cockpit target rebuilt from the real
	 * primitives (AppShell + Hero + CardGrid/Card + StatusDot + Inline + the
	 * recoloured Button), and (2) an isolated gallery so each primitive + the
	 * button variants can be eyeballed light+dark. VL2 re-skins the real cockpit
	 * to match this.
	 */
	import ArrowUpIcon from '@lucide/svelte/icons/arrow-up';
	import MoonIcon from '@lucide/svelte/icons/moon';
	import PlusIcon from '@lucide/svelte/icons/plus';
	import ScaleIcon from '@lucide/svelte/icons/scale';
	import ShieldIcon from '@lucide/svelte/icons/shield';
	import BriefcaseIcon from '@lucide/svelte/icons/briefcase';

	import { Button } from '$lib/components/ui/button/index.js';
	import AppShell from '$lib/lq-ai/components/primitives/AppShell.svelte';
	import Card from '$lib/lq-ai/components/primitives/Card.svelte';
	import CardGrid from '$lib/lq-ai/components/primitives/CardGrid.svelte';
	import Hero from '$lib/lq-ai/components/primitives/Hero.svelte';
	import Inline from '$lib/lq-ai/components/primitives/Inline.svelte';
	import Stack from '$lib/lq-ai/components/primitives/Stack.svelte';
	import StatusDot, { type DotStatus } from '$lib/lq-ai/components/primitives/StatusDot.svelte';

	let dark = $state(false);
	function toggleTheme() {
		dark = !dark;
		// Local, non-persisting toggle (scratch surface) — does not touch the
		// saved `theme` preference.
		const root = document.documentElement;
		root.classList.remove('dark', 'light');
		root.classList.add(dark ? 'dark' : 'light');
	}

	const AREAS = [
		{ name: 'Commercial', blurb: 'NDAs, MSAs, SaaS terms', status: 'completed', meta: '3 matters' },
		{ name: 'Privacy', blurb: 'GDPR, DPIAs, ROPA', status: 'running', meta: 'running' },
		{ name: 'M&A', blurb: 'Diligence, disclosure', status: 'idle', meta: 'idle' }
	] as const;

	const ICON = { Commercial: ScaleIcon, Privacy: ShieldIcon, 'M&A': BriefcaseIcon } as const;

	const MATTERS = [
		{
			title: 'NDA — Acme SaaS pilot',
			sub: 'Contract Snapshot · 12 docs · 6 cols',
			status: 'completed',
			label: 'Completed'
		},
		{
			title: 'MSA review — Northwind',
			sub: 'MSA Snapshot · 4 docs · 8 cols',
			status: 'running',
			label: 'Running'
		},
		{ title: 'SaaS terms — Project Iris', sub: 'ad-hoc · 1 doc', status: 'idle', label: 'Idle' }
	] as const;

	const RECENT = [
		{ title: 'NDA — Acme SaaS pilot', when: 'Commercial · 2m ago', active: true },
		{ title: 'MSA review — Northwind', when: 'Commercial · 1h ago', active: false },
		{ title: 'GDPR ROPA — Q2 programme', when: 'Privacy · yesterday', active: false },
		{ title: 'Disclosure schedule — Iris', when: 'M&A · 2d ago', active: false }
	];

	const CHIPS = ['Review this contract', 'Summarise key risks', 'Compare to our standard'];
	const BUTTON_VARIANTS = [
		'default',
		'outline',
		'secondary',
		'ghost',
		'link',
		'destructive'
	] as const;
	const ALL_DOTS: DotStatus[] = ['running', 'completed', 'failed', 'cancelled', 'idle'];
</script>

<div class="bg-background text-foreground h-screen" data-testid="vl-lab">
	<AppShell>
		{#snippet sidebar()}
			<div class="flex h-full flex-col px-3.5 py-5">
				<div class="px-2 pb-4 text-base font-bold tracking-tight">LQ.AI</div>
				<Button class="w-full justify-center"><PlusIcon /> New matter</Button>
				<p class="text-label text-muted-foreground px-2 pt-6 pb-2 uppercase">Recent</p>
				<Stack gap="none">
					{#each RECENT as m (m.title)}
						<button
							type="button"
							class="hover:bg-muted flex flex-col gap-0.5 rounded-md px-2 py-2 text-left transition-colors {m.active
								? 'text-foreground font-medium'
								: 'text-muted-foreground'}"
						>
							<span class="text-caption truncate">{m.title}</span>
							<span class="text-[11px] text-muted-foreground/70">{m.when}</span>
						</button>
					{/each}
				</Stack>
				<div class="border-border mt-auto flex items-center gap-2.5 border-t px-2 pt-3">
					<span
						class="bg-muted border-border grid size-7 place-items-center rounded-full border text-[11px] font-semibold"
						>A</span
					>
					<span class="text-caption leading-tight"
						>Arturs<small class="text-muted-foreground block">admin@lq.ai</small></span
					>
				</div>
			</div>
		{/snippet}

		{#snippet topbar()}
			<span class="text-caption text-muted-foreground"
				>Commercial <b class="text-foreground font-medium">· deep agent</b></span
			>
			<Button variant="outline" size="sm" class="rounded-full" onclick={toggleTheme}>
				<MoonIcon /> Theme
			</Button>
		{/snippet}

		<div class="mx-auto w-full max-w-[720px] px-7 pt-16 pb-20">
			<Stack gap="2xl">
				<!-- (1) the cockpit hero, rebuilt from primitives -->
				<Hero
					title="What are you working on?"
					subtitle="State the intent. Your practice-area deep agent picks its own tools, skills and playbooks — and works visibly."
				>
					<div
						class="border-input focus-within:border-foreground bg-background mt-1.5 flex w-full max-w-[600px] items-end gap-3 rounded-xl border px-4 py-3 transition-colors"
					>
						<textarea
							rows="1"
							aria-label="Describe your matter"
							placeholder="Draft a mutual NDA for a SaaS pilot, UK law, 2-year term…"
							class="text-foreground placeholder:text-muted-foreground/70 min-h-[26px] flex-1 resize-none border-0 bg-transparent text-sm outline-none"
						></textarea>
						<Button size="icon" class="rounded-full"><ArrowUpIcon /></Button>
					</div>
					<Inline gap="lg" wrap justify="center">
						{#each CHIPS as c (c)}
							<button
								type="button"
								class="text-caption text-muted-foreground hover:text-foreground border-b border-transparent pb-0.5 transition-colors hover:border-current"
								>{c}</button
							>
						{/each}
					</Inline>
				</Hero>

				<!-- (2) "Your practice" — the hairline CardGrid + dot-status -->
				<section>
					<p class="text-label text-muted-foreground mb-4 uppercase">Your practice</p>
					<CardGrid cols={3}>
						{#each AREAS as a (a.name)}
							{@const Icon = ICON[a.name]}
							<Card interactive>
								<Stack gap="sm">
									<Icon class="text-foreground size-[22px]" strokeWidth={1.7} />
									<!-- span, not <h3>: this Card renders as a <button>, and a heading is
									     not valid phrasing content inside one (the gallery's non-interactive
									     cards below keep real <h3>s). -->
									<span class="text-subheading text-foreground">{a.name}</span>
									<p class="text-caption text-muted-foreground flex-1">{a.blurb}</p>
									<StatusDot status={a.status} label={a.meta} />
								</Stack>
							</Card>
						{/each}
					</CardGrid>
				</section>

				<!-- (3) "Recent matters" — the hairline list + dot-status -->
				<section>
					<p class="text-label text-muted-foreground mb-4 uppercase">Recent matters</p>
					<div class="border-border border-t">
						{#each MATTERS as m (m.title)}
							<div class="border-border flex items-center justify-between border-b py-4">
								<div class="flex min-w-0 flex-col gap-0.5">
									<span class="text-foreground text-sm font-medium">{m.title}</span>
									<span class="text-caption text-muted-foreground">{m.sub}</span>
								</div>
								<StatusDot status={m.status} label={m.label} />
							</div>
						{/each}
					</div>
				</section>

				<!-- (4) isolated primitives gallery (lab-only — eyeball each) -->
				<section class="border-border border-t pt-10">
					<Stack gap="xl">
						<div>
							<p class="text-label text-muted-foreground mb-3 uppercase">Type scale (VL0 tokens)</p>
							<Stack gap="sm">
								<span class="text-display">Display 44</span>
								<span class="text-title">Title 24</span>
								<span class="text-heading">Heading 18</span>
								<span class="text-subheading">Subheading 18</span>
								<span class="text-body">Body 15 — the default reading size.</span>
								<span class="text-caption text-muted-foreground">Caption 13 — secondary meta.</span>
								<span class="text-label text-muted-foreground uppercase">Label 11 eyebrow</span>
							</Stack>
						</div>

						<div>
							<p class="text-label text-muted-foreground mb-3 uppercase">
								Button variants (inverting primary on ink)
							</p>
							<Inline gap="md" wrap>
								{#each BUTTON_VARIANTS as v (v)}
									<Button variant={v}>{v}</Button>
								{/each}
							</Inline>
						</div>

						<div>
							<p class="text-label text-muted-foreground mb-3 uppercase">StatusDot tones</p>
							<Inline gap="lg" wrap>
								{#each ALL_DOTS as s (s)}
									<StatusDot status={s} label={s} />
								{/each}
							</Inline>
						</div>

						<div>
							<p class="text-label text-muted-foreground mb-3 uppercase">
								Standalone bordered cards
							</p>
							<CardGrid cols={2}>
								<Card>
									<h3 class="text-subheading text-foreground mb-1">In a hairline grid</h3>
									<p class="text-caption text-muted-foreground">
										Cell on a 1px border plane, single outer radius.
									</p>
								</Card>
								<Card>
									<h3 class="text-subheading text-foreground mb-1">Flat, border-led</h3>
									<p class="text-caption text-muted-foreground">
										Shadows reserved for true float (spec §5).
									</p>
								</Card>
							</CardGrid>
						</div>
					</Stack>
				</section>
			</Stack>
		</div>
	</AppShell>
</div>
