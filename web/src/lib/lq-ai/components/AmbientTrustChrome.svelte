<script lang="ts">
  /**
   * AmbientTrustChrome — right side of the top bar.
   *
   * At Wave A: self-hosted pill + ⌘K hint. Tier pill is rendered by the
   * Workspace shell in Wave C (it's chat-scoped, not global). User menu
   * stays where the existing layout puts it.
   *
   * Personalization toggle "Trust pills → Dots" (spec §4.3) plumbs through
   * the `display` prop in a later wave; Wave A always renders labels.
   */
  import TrustPill from './TrustPill.svelte';
</script>

<!-- F2-M2: wrapper + ⌘K hint migrated off `--lq-*` to semantic tokens (the
     dark-mode fix). The TrustPill itself stays on its dark-bridged `--lq-*`
     tone palette — migrating its sage/slate/amber/red tones would need a new
     token scale (forbidden in F2) and touches ~15 consumers, so it is its own
     slice (see HANDOFF carry-overs). -->
<div class="inline-flex items-center gap-2">
  <TrustPill variant="secure" label="● self-hosted" />
  <span
    class="rounded-sm border border-border bg-muted px-1.5 py-px text-[11px] text-muted-foreground"
    aria-hidden="true">⌘K</span
  >
</div>
