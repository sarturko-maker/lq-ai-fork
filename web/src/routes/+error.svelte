<script lang="ts">
	import { page } from '$app/stores';
</script>

<div
	class="flex h-screen w-full flex-col items-center justify-center gap-2 text-gray-700 dark:text-gray-200"
>
	<div class="text-3xl font-semibold">{$page.status}</div>
	<div class="text-sm">{$page.error?.message ?? 'Something went wrong.'}</div>
	<a class="mt-2 text-sm underline" href="/lq-ai">Back to LQ.AI</a>
</div>
