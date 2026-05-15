import { defineConfig } from 'cypress';

export default defineConfig({
	e2e: {
		baseUrl: 'http://localhost:3000'
	},
	// Desktop-realistic viewport so the matter workspace fits — the chat
	// shell + matter rail + composer don't fit in Cypress' 1000x660 default
	// and the composer textarea ends up clipped by overflow:hidden.
	viewportWidth: 1440,
	viewportHeight: 900,
	video: true,
	// KB-attach and ingest round-trips can exceed Cypress' default 5s
	// response timeout. 90s absorbs worst-case ingest latency without
	// masking genuine hangs (the per-test timeout is still the main guard).
	responseTimeout: 90000
});
