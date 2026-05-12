<script lang="ts">
  import type { Project } from '$lib/lq-ai/types';

  export let matter: Project;
  export let onMatterUpdate: (next: Project) => void = () => {};
  export let onMatterArchived: () => void = () => {};
</script>

<!-- Placeholder: Commit B fills this section -->
<section class="mrm-section">
  <p class="lq-text-caption" style="color: var(--lq-text-tertiary);">Metadata loading…</p>
</section>

<style>
  @import '$lib/lq-ai/styles/practice.css';
  .mrm-section { display: flex; flex-direction: column; gap: var(--lq-space-2); }
</style>
