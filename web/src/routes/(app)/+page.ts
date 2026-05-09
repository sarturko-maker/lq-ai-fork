// LQ.AI: redirect the root path to the LQ.AI shell at /lq-ai.
//
// Per ADR 0009, the LQ.AI shell co-exists with the OpenWebUI shell
// (at the upstream-untouched routes under (app)). The original ADR
// 0009 design left this redirect as an operator opt-in; smoke-test
// feedback confirmed the default should be flipped — users hitting
// localhost:3000 expect the LQ.AI experience, not OpenWebUI's.
//
// The OpenWebUI shell remains reachable via deeper routes (e.g.
// /admin, /workspace, /chat/{id}). Operators who want OpenWebUI as
// the default can delete this `+page.ts` file to fall through to
// the upstream `(app)/+page.svelte`.

import { redirect } from '@sveltejs/kit';

export const load = () => {
	throw redirect(307, '/lq-ai');
};
