import typography from '@tailwindcss/typography';

/** @type {import('tailwindcss').Config} */
export default {
	// html.dark is set by app.html's inline theme script before first paint;
	// every dark: variant in the shell keys off this class.
	darkMode: 'class',
	content: ['./src/**/*.{html,js,svelte,ts}'],
	theme: {
		extend: {
			typography: {
				DEFAULT: {
					css: {
						// MessageBubble renders sanitized marked() output inside
						// `prose`; pre/code behavior is owned by the base layer
						// in app.css (pre-wrap + overflow), not by prose.
						pre: false,
						code: false,
						'pre code': false,
						'code::before': false,
						'code::after': false
					}
				}
			}
		}
	},
	plugins: [typography]
};
