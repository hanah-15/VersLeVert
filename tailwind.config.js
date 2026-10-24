/** @type {import('tailwindcss').Config} */
module.exports = {
  safelist: [
    'bg-porcelain',
    'bg-forest',
    'bg-carbon',
    'bg-palm',
    'bg-olive',
    'bg-sky',
    'bg-brick'
  ],
  content: [
    './templates/**/*.html',
    './accounts/templates/**/*.html',
    './challenges/templates/**/*.html',
    './events/templates/**/*.html',
    './gamification/templates/**/*.html',
    './places/templates/**/*.html',
    './waste/templates/**/*.html'
  ],
  theme: {
    extend: {
      colors: {
        porcelain: '#F8F7F2',
        forest: '#042E09',
        carbon: '#212121',
        palm: '#8A9B63',
        olive: '#B1C588',
        sky: '#89BCCF',
        brick: '#B3402F',
        paper: '#FFFFFF',
        mist: '#F0F3EB',
        line: '#DEE5D9',
        muted: '#657361',
        sand: '#EEE8DB',
        sun: '#E6C779',
        ink: '#23362B'
      },
      fontFamily: {
        heading: ['Fraunces', 'serif'],
        body: ['Nunito Sans', 'system-ui', 'sans-serif']
      },
      borderRadius: {
        'sm-ui': '16px',
        'md-ui': '20px',
        'lg-ui': '24px'
      },
      fontSize: {
        h1: ['44px', { lineHeight: '1.1' }],
        h2: ['28px', { lineHeight: '1.2' }],
        h3: ['20px', { lineHeight: '1.2' }],
        caption: ['13px', { lineHeight: '1.2' }]
      },
      maxWidth: {
        page: '1180px'
      },
      boxShadow: {
        card: '0 4px 24px -12px rgba(4, 46, 9, 0.12)',
        float: '0 16px 48px -16px rgba(4, 46, 9, 0.24)'
      }
    }
  },
  plugins: []
};
