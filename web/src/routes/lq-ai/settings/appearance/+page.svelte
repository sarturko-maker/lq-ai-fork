<script lang="ts">
	import { onMount } from 'svelte';
	import { preferences, setPreference, initPreferences } from '$lib/lq-ai/stores/preferences';
	import SettingsToggleGroup from '$lib/lq-ai/components/SettingsToggleGroup.svelte';
	import type { FeaturedTools, WorkspaceLayout, TrustPills, ProvenancePills } from '$lib/lq-ai/types';

	onMount(() => initPreferences());
</script>

<h2 class="lq-text-panel-h" style="margin-bottom: var(--lq-space-4);">Appearance</h2>
<p class="lq-text-body" style="color: var(--lq-text-secondary); margin-bottom: var(--lq-space-6);">
	Tune how LQ.AI presents itself. Brave choices are on by default; you can dial them back if you
	want less ceremony.
</p>

<SettingsToggleGroup
	label="Featured tools"
	description="Where Enhance Prompt, Skill Creator, and the launcher live."
	value={$preferences.featured_tools}
	options={[
		{
			value: 'prominent',
			label: 'Prominent cards on dashboard',
			description: 'Featured cards with descriptions, plus ⌘K launcher.'
		},
		{
			value: 'inline',
			label: 'Inline toolbar only',
			description: 'Small button row on every composer; less ceremony.'
		}
	]}
	onChange={(v) => setPreference('featured_tools', v as FeaturedTools)}
/>

<SettingsToggleGroup
	label="Workspace layout"
	description="How matter views compose (Wave C)."
	value={$preferences.workspace_layout}
	options={[
		{
			value: 'three_pane',
			label: 'Three panes',
			description: 'Matter rail · chat · outputs panel (default).'
		},
		{
			value: 'two_pane',
			label: 'Two panes',
			description: 'Chat · outputs panel; matter rail collapsed.'
		},
		{
			value: 'one_pane',
			label: 'Single pane',
			description: 'Chat only; docs open in a modal.'
		}
	]}
	onChange={(v) => setPreference('workspace_layout', v as WorkspaceLayout)}
/>

<SettingsToggleGroup
	label="Trust pills"
	description="The ambient indicators in the top bar."
	value={$preferences.trust_pills}
	options={[
		{
			value: 'labels',
			label: 'Labels',
			description: '"● self-hosted" — full label on the pill.'
		},
		{
			value: 'dots',
			label: 'Dots',
			description: 'Just the dot; label appears on hover.'
		}
	]}
	onChange={(v) => setPreference('trust_pills', v as TrustPills)}
/>

<SettingsToggleGroup
	label="Provenance pills"
	description="The per-message skill/tier/provider/audit row (Wave D)."
	value={$preferences.provenance_pills}
	options={[
		{
			value: 'always',
			label: 'Always shown',
			description: 'Pills under every AI reply.'
		},
		{
			value: 'collapsed',
			label: 'Collapsed; expand on hover',
			description: 'Single "🔍 details" affordance per reply.'
		}
	]}
	onChange={(v) => setPreference('provenance_pills', v as ProvenancePills)}
/>
