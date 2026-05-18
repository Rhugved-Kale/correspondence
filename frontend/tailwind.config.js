/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        // Editorial display face used in PeopleWiki.jsx for names and big
        // headers. System serif is fine; if we wanted something specific
        // we could pull in a webfont, but keeping zero font dependencies
        // makes local-dev startup instant.
        serif: ["ui-serif", "Georgia", "Cambria", "Times New Roman", "serif"],
      },
    },
  },
  plugins: [],
};
