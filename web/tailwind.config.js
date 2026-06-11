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
						// `prose`; code/pre styling is handled by the components.
						pre: false,
						code: false,
						'pre code': false,
						'code::before': false,
						'code::after': false
					}
				}
			},
			padding: {
				'safe-bottom': 'env(safe-area-inset-bottom)'
			},
			transitionProperty: {
				width: 'width'
			}
		}
	},
	plugins: [typography]
};
