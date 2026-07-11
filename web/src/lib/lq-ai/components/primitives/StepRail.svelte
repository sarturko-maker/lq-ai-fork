<!--
	StepRail — a horizontal step indicator for the guided setup wizard (B-7b,
	ADR-F067 D4). Token-driven (F013): a completed step inks solid
	(`--foreground`), the active step wears the scarce `--brand` accent, upcoming
	steps are muted outlines. Built new rather than reusing SkillWizardSection
	(legacy `--lq-*` teal). Presentation only — `steps`/`current` are the caller's
	state; a completed marker is a back-nav button when `onselect` is supplied.

	Responsive (design rule — collapse when narrow): the numbered dot row +
	connectors always render; the per-step text labels show from `md` up, and a
	single "Step N of M · {label}" line shows below on narrow screens.
-->
<script module lang="ts">
	export interface StepDef {
		key: string;
		label: string;
	}

	export type StepState = 'completed' | 'active' | 'upcoming';

	/** Where `index` sits relative to the `current` step — pure, for tests. */
	export function stepState(index: number, current: number): StepState {
		if (index < current) return 'completed';
		if (index === current) return 'active';
		return 'upcoming';
	}
</script>

<script lang="ts">
	let {
		steps,
		current,
		onselect = undefined
	}: {
		steps: StepDef[];
		current: number;
		/** Fired when a COMPLETED step's marker is activated (back-nav). */
		onselect?: (index: number) => void;
	} = $props();

	const currentLabel = $derived(steps[current]?.label ?? '');
</script>

<nav aria-label="Setup progress" class="w-full" data-testid="lq-setup-steprail">
	<ol class="flex items-start">
		{#each steps as step, i (step.key)}
			{@const state = stepState(i, current)}
			{@const clickable = state === 'completed' && !!onselect}
			<li class="relative flex flex-1 flex-col items-center gap-1.5">
				<!-- connector into this dot from the previous one (left-anchored at the
				     dot centre; `top-3.5` = half the 28px dot; z-0 under the marker). -->
				{#if i > 0}
					<div
						class="absolute right-1/2 top-3.5 z-0 h-px w-full {i <= current
							? 'bg-foreground'
							: 'bg-border'}"
						aria-hidden="true"
					></div>
				{/if}

				<button
					type="button"
					class="relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold transition-colors {state ===
					'completed'
						? 'border-foreground bg-foreground text-background'
						: state === 'active'
							? 'border-brand text-brand'
							: 'border-border bg-background text-muted-foreground'} {clickable
						? 'cursor-pointer hover:opacity-80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring'
						: 'cursor-default'}"
					disabled={!clickable}
					aria-current={state === 'active' ? 'step' : undefined}
					aria-label={`Step ${i + 1}: ${step.label}${state === 'completed' ? ' (completed)' : ''}`}
					onclick={() => {
						if (clickable && onselect) onselect(i);
					}}
				>
					{#if state === 'completed'}✓{:else}{i + 1}{/if}
				</button>

				<span
					class="hidden max-w-[8rem] truncate px-1 text-center text-xs md:block {state === 'active'
						? 'font-medium text-foreground'
						: 'text-muted-foreground'}"
				>
					{step.label}
				</span>
			</li>
		{/each}
	</ol>

	<!-- narrow-screen current-step line (labels are hidden below md) -->
	<p class="mt-2 text-center text-xs text-muted-foreground md:hidden">
		Step {current + 1} of {steps.length} · <span class="text-foreground">{currentLabel}</span>
	</p>
</nav>
