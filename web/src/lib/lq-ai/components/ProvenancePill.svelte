<script context="module" lang="ts">
  /**
   * ProvenancePill — pill primitive attached to AI messages.
   * Wave A defines the contract; Wave D wires it into the message renderer.
   * See spec §5.2.
   */
  export type ProvenanceKind = 'skill' | 'tier' | 'provider' | 'kb' | 'audit' | 'enhanced';

  const KIND_ICON: Record<ProvenanceKind, string> = {
    skill: '🛠️',
    tier: '🔒',
    provider: '🧠',
    kb: '📎',
    audit: '📜',
    enhanced: '✨'
  };

  export function iconFor(kind: ProvenanceKind): string {
    return KIND_ICON[kind];
  }

  export type ProvenanceTone = 'sage' | 'slate' | 'amber';

  export function toneFor(kind: ProvenanceKind, tierMismatch: boolean): ProvenanceTone {
    if (kind === 'tier') return tierMismatch ? 'amber' : 'slate';
    return 'sage';
  }
</script>

<script lang="ts">
  export let kind: ProvenanceKind;
  export let summary: string;
  export let tierMismatch = false;
  export let onTap: (() => void) | undefined = undefined;

  $: tone = toneFor(kind, tierMismatch);
  $: icon = iconFor(kind);
</script>

<button
  type="button"
  class="lq-prov-pill lq-prov-tone-{tone}"
  aria-label="{kind}: {summary}"
  on:click={onTap}
>
  <span class="lq-prov-icon" aria-hidden="true">{icon}</span>
  <span class="lq-prov-summary">{summary}</span>
</button>

<style>
  .lq-prov-pill {
    display: inline-flex;
    align-items: center;
    gap: var(--lq-space-1);
    padding: 2px 8px;
    border-radius: var(--lq-radius-pill);
    font-size: 11px;
    line-height: 1.4;
    border: 1px solid transparent;
    background: transparent;
    cursor: pointer;
  }
  .lq-prov-icon { font-size: 11px; }
  .lq-prov-summary { font-weight: 500; }
  .lq-prov-tone-sage  { background: var(--lq-accent-soft); color: var(--lq-accent); border-color: var(--lq-accent-border); }
  .lq-prov-tone-slate { background: var(--lq-tier-soft);   color: var(--lq-tier);   border-color: var(--lq-tier-border); }
  .lq-prov-tone-amber { background: var(--lq-warn-soft);   color: var(--lq-warn);   border-color: var(--lq-warn-border); }
  .lq-prov-pill:hover { filter: brightness(0.97); }
  .lq-prov-pill:focus-visible { outline: 2px solid var(--lq-accent); outline-offset: 2px; }
</style>
