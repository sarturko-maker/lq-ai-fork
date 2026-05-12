<script lang="ts">
  import type { Project } from '$lib/lq-ai/types';

  export let matter: Project;
  export let onMatterUpdate: (next: Project) => void = () => {};
</script>

<!-- Placeholder: Commit D fills this section -->
<section class="mrs-section">
  <p class="lq-text-caption" style="color: var(--lq-text-tertiary);">Skills loading…</p>
</section>

<style>
  @import '$lib/lq-ai/styles/practice.css';
  .mrs-section { display: flex; flex-direction: column; gap: var(--lq-space-2); }
</style>
