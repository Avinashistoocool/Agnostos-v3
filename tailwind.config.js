module.exports = {
  content: ['./web/index.html', './web/app.html', './web/app.js', './web/researchers.js', './web/softly.js'],
  theme: {
    extend: {
      colors: {
        cream: '#FDFCF8', sage: '#E8EFE8', lavender: '#EFEDF4',
        coral: '#FFB7B2', ink: '#292524', muted: '#78716C',
        rose: '#FFE4E1', lilac: '#E6E6FA',
      },
      fontFamily: { sans: ['Outfit', 'sans-serif'], hand: ['"Reenie Beanie"', 'cursive'] },
      boxShadow: { soft: '0 4px 20px -2px rgba(0,0,0,0.05)' },
      letterSpacing: { tightish: '-0.025em' },
    },
  },
};
