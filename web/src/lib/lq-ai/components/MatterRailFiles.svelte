<script lang="ts">
  import type { Project } from '$lib/lq-ai/types';

  export let matter: Project;
  export let onMatterUpdate: (next: Project) => void = () => {};
</script>

<!-- Placeholder: Commit C fills this section -->
<section class="mrf-section">
  <p class="lq-text-caption" style="color: var(--lq-text-tertiary);">Files loading…</p>
</section>

<style>
  @import '$lib/lq-ai/styles/practice.css';
  .mrf-section { display: flex; flex-direction: column; gap: var(--lq-space-2); }
</style>
