<!-- web/src/lib/lq-ai/components/SkillTryItTab.svelte -->
<script lang="ts">
  import SkillTryItPane from './SkillTryItPane.svelte';
  export let skillSlug: string;
</script>

<SkillTryItPane {skillSlug} source="tryit-tab" />
