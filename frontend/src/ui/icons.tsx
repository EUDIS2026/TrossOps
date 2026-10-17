import type { SVGProps } from 'react'

const base = (props: SVGProps<SVGSVGElement>) => ({ width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true, ...props })
type P = SVGProps<SVGSVGElement>

export const Icon = {
  layers: (p: P) => <svg {...base(p)}><path d="M12 3 3 8l9 5 9-5-9-5Z" /><path d="m3 13 9 5 9-5" /><path d="m3 17.5 9 5 9-5" /></svg>,
  bell: (p: P) => <svg {...base(p)}><path d="M6 9a6 6 0 0 1 12 0v4l2 3H4l2-3V9Z" /><path d="M10 20a2 2 0 0 0 4 0" /></svg>,
  decide: (p: P) => <svg {...base(p)}><path d="M4 6h10M4 12h16M4 18h7" /><path d="m17 15 2 2 4-4" /></svg>,
  report: (p: P) => <svg {...base(p)}><path d="M5 4h11l3 3v13H5z" /><path d="M8 11h8M8 15h8" /></svg>,
  search: (p: P) => <svg {...base(p)}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.3-4.3" /></svg>,
  cube: (p: P) => <svg {...base(p)}><path d="M12 3 4 7.5v9L12 21l8-4.5v-9L12 3Z" /><path d="M4 7.5 12 12l8-4.5M12 12v9" /></svg>,
  help: (p: P) => <svg {...base(p)}><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 1-1 1.7M12 17h.01" /></svg>,
  close: (p: P) => <svg {...base(p)}><path d="m6 6 12 12M18 6 6 18" /></svg>,
  chevron: (p: P) => <svg {...base(p)}><path d="m6 9 6 6 6-6" /></svg>,
  right: (p: P) => <svg {...base(p)}><path d="m9 6 6 6-6 6" /></svg>,
  target: (p: P) => <svg {...base(p)}><circle cx="12" cy="12" r="7" /><circle cx="12" cy="12" r="2" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></svg>,
  live: (p: P) => <svg {...base(p)}><path d="M5 12h3l2-6 4 12 2-6h3" /></svg>,
  mountain: (p: P) => <svg {...base(p)}><path d="m3 19 6-10 4 6 2-3 6 7H3Z" /></svg>,
  check: (p: P) => <svg {...base(p)}><path d="m5 12 4 4L19 7" /></svg>,
  play: (p: P) => <svg {...base(p)}><path d="M7 5v14l11-7L7 5Z" /></svg>,
  pause: (p: P) => <svg {...base(p)}><path d="M8 5v14M16 5v14" /></svg>,
  back: (p: P) => <svg {...base(p)}><path d="M11 5l-7 7 7 7M4 12h16" /></svg>,
  sparkle: (p: P) => <svg {...base(p)}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6" /></svg>,
  route: (p: P) => <svg {...base(p)}><circle cx="6" cy="18" r="2.2" /><circle cx="18" cy="6" r="2.2" /><path d="M8 18h6a3 3 0 0 0 0-6h-4a3 3 0 0 1 0-6h6" /></svg>,
  satellite: (p: P) => <svg {...base(p)}><path d="m13 7 4 4M7 13l4 4" /><path d="m9 9 6 6M15 3l6 6-3 3-6-6 3-3ZM3 15l6 6 3-3-6-6-3 3Z" /></svg>,
  map: (p: P) => <svg {...base(p)}><path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Z" /><path d="M9 4v14M15 6v14" /></svg>,
  scenario: (p: P) => <svg {...base(p)}><path d="M12 3v3M12 18v3M4.2 7.5l2.6 1.5M17.2 15l2.6 1.5M4.2 16.5 6.8 15M17.2 9l2.6-1.5" /><circle cx="12" cy="12" r="4" /></svg>,
  plug: (p: P) => <svg {...base(p)}><path d="M9 3v5M15 3v5M7 8h10v3a5 5 0 0 1-10 0V8ZM12 16v5" /></svg>,
  plane: (p: P) => <svg {...base(p)}><path d="M12 3c.8 0 1.4.7 1.4 1.5V9l7 4v2l-7-2v4l2 1.5V20l-3.4-1-3.4 1v-1.5l2-1.5v-4l-7 2v-2l7-4V4.5C10.6 3.7 11.2 3 12 3Z" /></svg>,
  ship: (p: P) => <svg {...base(p)}><path d="M4 15h16l-2 5H6l-2-5ZM6 15V9h12v6M10 9V5h4v4" /></svg>,
  eye: (p: P) => <svg {...base(p)}><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></svg>,
  shield: (p: P) => <svg {...base(p)}><path d="M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6l-7-3Z" /></svg>,
  fast: (p: P) => <svg {...base(p)}><path d="M4 6v12l7-6-7-6ZM12 6v12l7-6-7-6Z" /></svg>,
}
