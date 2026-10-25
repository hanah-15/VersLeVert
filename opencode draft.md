# opencode draft

This document records exactly what was done to apply the glassmorphism redesign described in `opencode.md`, so you can revert/understand the changes.

## Goal (from opencode.md)
Redesign the Django home template for "Vers le Vert" in LIGHT FROSTED GLASSMORPHISM style using ONLY Tailwind utility classes. Keep all Django logic exactly as-is (extends/load/url/if/user.waste_impact/include blocks/ids/aria/French copy). Add minimal config/JS/docs.

## Files touched (reversible)
- `tailwind.config.js` — extended (additions only; nothing removed)
- `templates/home.html` — fully rewritten to glassmorphism style (Django logic/blocks/ids/urls/filters/includes preserved)
- `static/css/tailwind.css` — regenerated via `npm run build:css` (build artifact)
- `opencode draft.md` — this history file (created)

Files NOT modified (kept intact):
- `templates/ui/base.html`, `templates/ui/navigation.html`, `templates/base.html` (navbar redesign deferred to base-level migration; see patterns below)
- All other templates/CSS/JS except build output

## 1) tailwind.config.js additions (only)
Extended `theme.extend`:
```js
colors: {
  // ...existing...
  'palm-deep': '#5C6B3C',
  'palm-soft': '#C9D5AE',
},
keyframes: {
  drift:   { '0%': { transform: 'scale(1.04) translate3d(0,0,0)' }, '100%': { transform: 'scale(1.09) translate3d(-1.2%, -0.8%, 0)' } },
  float:   { '0%,100%': { transform: 'translateY(0)' }, '50%': { transform: 'translateY(-10px)' } },
  reveal:  { '0%': { opacity: '0', transform: 'translateY(24px)', filter: 'blur(6px)' }, '100%': { opacity: '1', transform: 'translateY(0)', filter: 'blur(0)' } },
  breathe: { '0%,100%': { opacity: '0.55' }, '50%': { opacity: '0.9' } }
},
animation: {
  drift:  'drift 40s ease-in-out infinite alternate',
  float:  'float 9s ease-in-out infinite',
  reveal: 'reveal 1.1s cubic-bezier(0.22, 1, 0.36, 1) both',
  breathe:'breathe 7s ease-in-out infinite'
}
```

## 2) templates/home.html (key changes)
- Added `{% block extra_head %}` with Fraunces+Nunito Sans Google Fonts (needed for `font-[Fraunces,...]` / `font-[Nunito_Sans,...]` on this page).
- Added fixed decorative background at top of `{% block content %}` (aria-hidden, object-cover, veil gradients, radial glow; `motion-safe:animate-drift`, `max-md:animate-none`). Uses `{% static 'images/forest-path.webp' %}` with width/height/decoding/fetchpriority.
- Added `<noscript><style>[data-reveal]{opacity:1!important;transform:none!important}</style></noscript>`.
- Hero (min-h-[88vh], max-w-page, lg:grid-cols-[1.05fr_0.95fr]): GLASS-STRONG left card (with decorative breathe glow), right column has only GLASS-SUBTLE label and GLASS seal (112px, `motion-safe:animate-float`). Staggered hero reveals via `motion-safe:animate-reveal` + `[animation-delay:...]`. All Django conditionals/urls/includes preserved.
- Sections restructured to glass (GLASS/GLASS-STRONG/GLASS-SUBTLE with `backdrop-blur-*/backdrop-saturate-150`, borders/white tints, shadows). Headings use `!font-[Fraunces,serif]` to override site `.app-content h1/h2/h3` rules.
- Action paths (3 cards) as GLASS + GLASS-HOVER, numbers 01/02/03, icons in palm circles, links with arrow slide on group-hover. "community-more" row as GLASS-SUBTLE pill container.
- Story (lg:grid-cols-2): title card GLASS-STRONG + copy card GLASS-STRONG with 3-step list; step numbers 40px palm circles, thin vertical connector via arbitrary pseudo-variants between steps.
- Impact (authenticated): `{% waste_impact user as impact %}` preserved; GLASS-STRONG wide card with 3-col stats grid divided by `divide-white/50`, numbers in `font-[Fraunces,serif] text-4xl`, units `text-palm-deep`.
- Invitation (guest): GLASS-STRONG with `bg-gradient-to-br from-palm/25 to-white/40`, palm leaf circle, light button.
- Reveal-on-scroll script at end of `{% block content %}`: IntersectionObserver (`threshold:0.15`, `rootMargin:'0px 0px -10% 0px'`, unobserve after reveal). Staggers by 120ms via `data-reveal-index`. Adds `motion-safe:animate-reveal`/`animate-reveal`. Falls back to revealing all if no IO/support.
- Footer overridden in `{% block footer %}` to GLASS-SUBTLE style (French copy preserved).

## 3) Reveal-on-scroll script
Added inline (~15 lines) as above. Elements below hero use `data-reveal` + `opacity-0 translate-y-6` + `motion-reduce:opacity-100 motion-reduce:translate-y-0`. Cards in grids use `data-reveal-index`.

## 4) How to reuse patterns elsewhere (5 lines)
1. **Glass recipes**: `bg-white/40 backdrop-blur-xl backdrop-saturate-150 border border-white/50 shadow-glass rounded-lg-ui supports-[not(backdrop-filter:blur(1px))]:bg-porcelain/95` (GLASS), use `bg-white/60` + `backdrop-blur-2xl` for strong, `bg-white/25 backdrop-blur-md rounded-full` for subtle.
2. **Colors/contrast**: use `palm` for fills/icons/large accents, `palm-deep` for small text/links/eyebrows; text on palm buttons = `text-forest`. Add `palm-deep`/`palm-soft` to config if missing.
3. **Motion**: add drift/float/reveal/breathe keyframes+animations to tailwind.config.js, use `motion-safe:animate-*`, respect `motion-reduce:animate-none motion-reduce:opacity-100 motion-reduce:translate-y-0`, and add IntersectionObserver reveal with stagger + `<noscript>` fallback.
4. **Type/spacing**: `font-[Fraunces,serif]` for headings (override app rules with `!` if needed), `font-[Nunito_Sans,sans-serif]`/`font-ui`, generous section gaps (`py-20 md:py-28`), `max-w-page`.
5. **Interaction/a11y**: buttons/cards `!transition-all !duration-500 !ease-out` where site base overrides transitions, visible `focus-visible:ring-4 focus-visible:!ring-palm/40`, reduce blur on mobile (`backdrop-blur-lg md:backdrop-blur-xl`), avoid `background-attachment:fixed` (use fixed inset-0 bg layer).

**Note (navbar):** Navbar was left unchanged in `templates/ui/navigation.html` to keep this change reversible and avoid breaking other pages. Apply glass navbar pattern (sticky glass-subtle, palm accents, focus rings) at base level during full migration using the same recipes above.

## How to revert
```bash
git checkout -- tailwind.config.js templates/home.html
# restore old CSS if desired
git checkout -- static/css/tailwind.css
rm "opencode draft.md"
# rebuild if needed
npm run build:css
```
Or manually restore from backups. The home page will return to pre-glass styles and navbar/footer behavior.
