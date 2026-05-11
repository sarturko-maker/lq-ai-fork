<script lang="ts">
  /**
   * AmbientFooter — bottom-of-chat reassurance bar.
   *
   * Wave A renders provider + tier + a static "audit on" pill. Wave B
   * wires audit-health from /api/v1/trust/audit-health (backend gap §9.1).
   * Wave D adds the "external turns today" counter.
   */
  import TrustPill from './TrustPill.svelte';

  export let provider: string;
  export let tier: string;
</script>

<footer class="lq-footer" aria-label="Chat status">
  <TrustPill variant="provider" label="● {provider} · {tier}" />
  <!-- Audit-health wiring (Wave B backend dep): replace static label
       with derived state once /api/v1/trust/audit-health ships. -->
  <TrustPill variant="audit" label="✓ audit on" />
</footer>

<style>
  .lq-footer {
    display: flex; align-items: center; gap: var(--lq-space-3);
    padding: var(--lq-space-2) var(--lq-space-4);
    border-top: 1px solid var(--lq-border);
    background: var(--lq-inset);
    font-size: 12px;
  }
</style>
