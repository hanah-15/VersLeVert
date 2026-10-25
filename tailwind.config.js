/** @type {import('tailwindcss').Config} */
module.exports = {
  safelist: [
    'bg-porcelain',
    'bg-forest',
    'bg-carbon',
    'bg-palm',
    'bg-olive',
    'rounded-2xl',
    'peer',
    'w-full',
    'rounded-full',
    'border-white/40',
    'bg-white/30',
    'px-5',
    'py-3.5',
    'text-forest',
    'placeholder:text-forest/50',
    'backdrop-blur-md',
    'transition-all',
    'duration-500',
    'hover:border-palm/50',
    'focus:border-palm',
    'focus:bg-white/45',
    'focus:outline-none',
    'focus:ring-4',
    'focus:ring-palm/30',
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
        'palm-deep': '#5C6B3C',
        'palm-soft': '#C9D5AE',
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
        ui: ['DM Sans', 'Segoe UI', 'sans-serif'],
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
        glass: 'inset 0 1px 0 rgba(255, 255, 255, 0.4), 0 20px 60px -32px rgba(4, 46, 9, 0.35)',
        'glass-lg':
          '0 30px 80px -30px rgba(4,46,9,0.45), 0 8px 24px -12px rgba(4,46,9,0.18), ' +
          'inset 0 1px 0 rgba(255,255,255,0.85), inset 1px 0 0 rgba(255,255,255,0.45), ' +
          'inset 0 -1px 0 rgba(255,255,255,0.15)',
        card: '0 4px 24px -12px rgba(4, 46, 9, 0.12)',
        float: '0 16px 48px -16px rgba(4, 46, 9, 0.24)'
      },
      keyframes: {
        drift: {
          '0%': { transform: 'scale(1.04) translate3d(0,0,0)' },
          '100%': { transform: 'scale(1.09) translate3d(-1.2%, -0.8%, 0)' }
        },
        float: {
          '0%,100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' }
        },
        reveal: {
          '0%': { opacity: '0', transform: 'translateY(24px)', filter: 'blur(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)', filter: 'blur(0)' }
        },
        breathe: {
          '0%,100%': { opacity: '0.55' },
          '50%': { opacity: '0.9' }
        }
      },
      animation: {
        drift: 'drift 40s ease-in-out infinite alternate',
        float: 'float 9s ease-in-out infinite',
        reveal: 'reveal 1.1s cubic-bezier(0.22, 1, 0.36, 1) both',
        breathe: 'breathe 7s ease-in-out infinite'
      },
      backgroundImage: {
        'glass-sheen': 'linear-gradient(135deg, rgba(255,255,255,0.55) 0%, rgba(255,255,255,0) 38%)',
        noise: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.5'/%3E%3C/svg%3E\")"
      }
    }
  },
  plugins: []
};
