<script lang="ts">
	/**
	 * EnhancePromptExpansion — inline expansion panel shown between the composer
	 * and AmbientFooter after the user clicks ✨.
	 *
	 * State machine:
	 *   closed   → nothing shown
	 *   loading  → spinner + "Enhancing…"
	 *   shown    → two-column Original / Enhanced card diff + action buttons
	 *   skipped  → "No expansion needed" message + Got it button
	 *   error    → error message + Try again / Dismiss
	 *
	 * The parent calls `open()` to trigger the API call. Callbacks let the
	 * parent update composerText and handle dismissal without this component
	 * reaching into the DOM.
	 *
	 * R7: migrated to Svelte 5 runes + semantic tokens. The three legacy button
	 * families (`.lq-btn-primary/secondary/ghost`) collapse onto the shared
	 * shadcn `Button` primitive — the runes conversion is what lets `onclick`
	 * forward to it (a legacy `on:click` on a runes child would not). No `<style>`
	 * block; the `max-[640px]` single-column reflow is now Tailwind's `sm:`. The
	 * state-machine variable is named `panel` (not `state`) to avoid colliding
	 * with the `$state` rune in the Svelte TS tooling.
	 */
	import { enhance, recordOutcome } from '$lib/lq-ai/api/enhancePrompt';
	import TrustPill from './TrustPill.svelte';
	import { Button } from '$lib/components/ui/button';

	type ExpansionState =
		| { kind: 'closed' }
		| { kind: 'loading'; original: string }
		| {
				kind: 'shown';
				original: string;
				enhanced: string;
				reasoning: string[];
				preview?: string;
				interactionId: string;
				tier: number | null;
				provider: string | null;
		  }
		| { kind: 'skipped'; original: string; skipReason: string; interactionId: string }
		| { kind: 'error'; original: string; message: string };

	let {
		originalText,
		chatId = null,
		onUseEnhanced = () => undefined,
		onEditEnhanced = () => undefined,
		onKeepOriginal = () => undefined,
		onDismiss = () => undefined
	}: {
		originalText: string;
		chatId?: string | null;
		onUseEnhanced?: (enhanced: string, interactionId: string) => void;
		onEditEnhanced?: (enhanced: string, interactionId: string) => void;
		onKeepOriginal?: (interactionId: string | null) => void;
		onDismiss?: () => void;
	} = $props();

	/**
	 * §7.1 — first-time JIT onboarding strip. Shows once on the user's first
	 * post-enhance shown state and persists dismissal in localStorage so
	 * subsequent enhancements don't re-show it.
	 */
	const JIT_SEEN_KEY = 'lq_ai_jit_enhance_seen';

	function readJitSeen(): boolean {
		try {
			return localStorage.getItem(JIT_SEEN_KEY) === 'true';
		} catch {
			return false;
		}
	}

	let jitDismissed = $state(readJitSeen());
	let panel = $state<ExpansionState>({ kind: 'closed' });

	function dismissJit(): void {
		jitDismissed = true;
		try {
			localStorage.setItem(JIT_SEEN_KEY, 'true');
		} catch {
			// best-effort: storage/telemetry unavailable is non-fatal
		}
	}

	function setOnboardedFlag(): void {
		try {
			localStorage.setItem('lq-ai:onboarded:enhance', 'true');
		} catch {
			// best-effort: storage/telemetry unavailable is non-fatal
		}
	}

	export async function open(): Promise<void> {
		const text = originalText;
		if (!text.trim()) return;
		panel = { kind: 'loading', original: text };
		try {
			const res = await enhance({
				raw_input: text,
				chat_id: chatId ?? undefined
			});
			if (res.expansion_applied) {
				panel = {
					kind: 'shown',
					original: text,
					enhanced: res.expanded_prompt,
					reasoning: res.reasoning,
					preview: res.preview_to_user,
					interactionId: res.interaction_id,
					tier: res.routed_inference_tier ?? null,
					provider: res.routed_provider ?? null
				};
			} else {
				panel = {
					kind: 'skipped',
					original: text,
					skipReason: res.skip_reason ?? 'no reason provided',
					interactionId: res.interaction_id
				};
			}
		} catch (e) {
			const original = (panel as { kind: 'loading'; original: string }).original ?? text;
			panel = {
				kind: 'error',
				original,
				message: e instanceof Error ? e.message : 'Unknown error'
			};
		}
	}

	async function handleUseEnhanced(): Promise<void> {
		if (panel.kind !== 'shown') return;
		const { enhanced, interactionId } = panel;
		panel = { kind: 'closed' };
		setOnboardedFlag();
		onUseEnhanced(enhanced, interactionId);
		try {
			await recordOutcome(interactionId, { used: true, edited_before_use: false });
		} catch {
			// best-effort: storage/telemetry unavailable is non-fatal
		}
	}

	async function handleEditEnhanced(): Promise<void> {
		if (panel.kind !== 'shown') return;
		const { enhanced, interactionId } = panel;
		panel = { kind: 'closed' };
		setOnboardedFlag();
		onEditEnhanced(enhanced, interactionId);
		try {
			await recordOutcome(interactionId, { used: true, edited_before_use: true });
		} catch {
			// best-effort: storage/telemetry unavailable is non-fatal
		}
	}

	async function handleKeepOriginal(): Promise<void> {
		if (panel.kind !== 'shown') return;
		const { interactionId } = panel;
		panel = { kind: 'closed' };
		setOnboardedFlag();
		onKeepOriginal(interactionId);
		try {
			await recordOutcome(interactionId, { used: false });
		} catch {
			// best-effort: storage/telemetry unavailable is non-fatal
		}
	}

	async function handleSkippedDismiss(): Promise<void> {
		if (panel.kind !== 'skipped') return;
		const { interactionId } = panel;
		panel = { kind: 'closed' };
		setOnboardedFlag();
		onKeepOriginal(interactionId);
		try {
			await recordOutcome(interactionId, { used: false });
		} catch {
			// best-effort: storage/telemetry unavailable is non-fatal
		}
	}

	function handleDismiss(): void {
		const prev = panel;
		panel = { kind: 'closed' };
		if (prev.kind === 'shown') {
			// best-effort telemetry; panel is already closed, so fire-and-forget.
			// `.catch` (not a sync try/catch) is what actually swallows the async
			// rejection — recordOutcome returns a Promise.
			void recordOutcome(prev.interactionId, { used: false }).catch(() => {});
		}
		onDismiss();
	}

	function handleRetry(): void {
		void open();
	}
</script>

{#if panel.kind !== 'closed'}
	<div
		class="flex flex-col gap-3 rounded-lg border border-border bg-card p-3"
		data-testid="lq-ai-enhance-panel"
	>
		{#if panel.kind === 'loading'}
			<div class="flex items-center gap-2 py-2" data-testid="lq-ai-enhance-loading">
				<span
					class="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-muted border-t-primary"
					aria-hidden="true"
				></span>
				<span class="text-xs text-muted-foreground">Enhancing… ✨</span>
			</div>
		{:else if panel.kind === 'shown'}
			{#if !jitDismissed}
				<div
					class="flex items-center justify-between gap-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-amber-700 dark:text-amber-300"
					data-testid="lq-ai-enhance-jit"
				>
					<span class="flex-1 text-xs">
						Tip: ✨ rewrites your prompt so the AI has more to work with. Pick
						<strong>Use enhanced</strong>, tweak with <strong>Edit enhanced</strong>, or
						<strong>Keep original</strong>. (⌘E)
					</span>
					<Button
						variant="ghost"
						size="sm"
						class="shrink-0"
						onclick={dismissJit}
						data-testid="lq-ai-enhance-jit-dismiss"
						aria-label="Dismiss tip"
					>
						Got it
					</Button>
				</div>
			{/if}
			<div class="flex items-center justify-between">
				<span class="text-[13px] font-semibold text-foreground">Prompt Enhancement</span>
				<div class="flex items-center gap-2">
					{#if panel.tier != null}
						<TrustPill variant="tier" label="Tier {panel.tier}" />
					{/if}
					<Button
						variant="ghost"
						size="icon-sm"
						class="text-lg leading-none text-muted-foreground"
						aria-label="Dismiss enhancement"
						onclick={handleDismiss}
					>
						×
					</Button>
				</div>
			</div>

			<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
				<div
					class="flex flex-col gap-2 rounded-md border border-border bg-card p-3 opacity-60"
					data-testid="lq-ai-enhance-original"
				>
					<div class="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
						Original
					</div>
					<p class="m-0 text-[13px] break-words whitespace-pre-wrap text-foreground">
						{panel.original}
					</p>
				</div>
				<div
					class="flex flex-col gap-2 rounded-md border border-primary/40 bg-accent p-3"
					data-testid="lq-ai-enhance-enhanced"
				>
					<div class="text-[11px] font-semibold tracking-wider text-accent-foreground uppercase">
						Enhanced ✨
					</div>
					<p class="m-0 text-[13px] break-words whitespace-pre-wrap text-foreground">
						{panel.enhanced}
					</p>
					{#if panel.reasoning.length > 0}
						<ul class="m-0 flex flex-col gap-0.5 pl-4">
							{#each panel.reasoning as bullet}
								<li class="text-[11px] text-muted-foreground">{bullet}</li>
							{/each}
						</ul>
					{/if}
				</div>
			</div>

			<div class="flex flex-wrap items-center gap-2">
				<Button onclick={handleUseEnhanced} data-testid="lq-ai-enhance-use">Use enhanced</Button>
				<Button variant="outline" onclick={handleEditEnhanced} data-testid="lq-ai-enhance-edit">
					Edit enhanced
				</Button>
				<Button variant="ghost" onclick={handleKeepOriginal} data-testid="lq-ai-enhance-keep">
					Keep original
				</Button>
			</div>
		{:else if panel.kind === 'skipped'}
			<div class="flex flex-wrap items-center gap-3" data-testid="lq-ai-enhance-skipped">
				<span class="text-xs text-muted-foreground">
					No expansion needed — your prompt is already structured. ({panel.skipReason})
				</span>
				<Button
					variant="outline"
					onclick={handleSkippedDismiss}
					data-testid="lq-ai-enhance-skipped-ok"
				>
					Got it
				</Button>
			</div>
		{:else if panel.kind === 'error'}
			<div class="flex flex-col gap-2" data-testid="lq-ai-enhance-error">
				<span class="text-xs text-destructive dark:text-red-300">
					Enhance Prompt failed: {panel.message}
				</span>
				<div class="flex gap-2">
					<Button variant="outline" onclick={handleRetry} data-testid="lq-ai-enhance-retry">
						Try again
					</Button>
					<Button variant="ghost" onclick={handleDismiss} data-testid="lq-ai-enhance-error-dismiss">
						Dismiss
					</Button>
				</div>
			</div>
		{/if}
	</div>
{/if}
