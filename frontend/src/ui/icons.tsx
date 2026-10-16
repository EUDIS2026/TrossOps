import type { SVGProps } from 'react'

const base = (props: SVGProps<SVGSVGElement>) => ({ width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true, ...props })

export const Icon = {
  layers: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 3 3 8l9 5 9-5-9-5Z" /><path d="m3 13 9 5 9-5" /><path d="m3 17.5 9 5 9-5" /></svg>,
  bell: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M6 9a6 6 0 0 1 12 0v4l2 3H4l2-3V9Z" /><path d="M10 20a2 2 0 0 0 4 0" /></svg>,
  decide: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M4 6h10M4 12h16M4 18h7" /><path d="m17 15 2 2 4-4" /></svg>,
  report: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M5 4h11l3 3v13H5z" /><path d="M8 11h8M8 15h8" /></svg>,
  search: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.3-4.3" /></svg>,
  cube: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 3 4 7.5v9L12 21l8-4.5v-9L12 3Z" /><path d="M4 7.5 12 12l8-4.5M12 12v9" /></svg>,
  globe: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18" /></svg>,
  help: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 1-1 1.7M12 17h.01" /></svg>,
  close: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="m6 6 12 12M18 6 6 18" /></svg>,
  chevron: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="m6 9 6 6 6-6" /></svg>,
  target: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><circle cx="12" cy="12" r="7" /><circle cx="12" cy="12" r="2" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></svg>,
  live: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M5 12h3l2-6 4 12 2-6h3" /></svg>,
  mountain: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="m3 19 6-10 4 6 2-3 6 7H3Z" /></svg>,
  check: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="m5 12 4 4L19 7" /></svg>,
  play: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M7 5v14l11-7L7 5Z" /></svg>,
  back: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M11 5l-7 7 7 7M4 12h16" /></svg>,
  sparkle: (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6" /></svg>,
}
