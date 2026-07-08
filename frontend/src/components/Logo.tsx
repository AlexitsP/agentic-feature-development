/**
 * SLH AI Hub brand — built around the existing Swiss Learning Hub identity.
 *
 * Brand colors are taken from SLH's official logo SVGs (red mark + orange wordmark):
 *   SLH_RED    #FF0000   — the square mark
 *   SLH_ORANGE #ef7c00   — the wordmark / accent
 *
 * `SlhMark` is SLH's own square mark (2×2 grid, top-left tilted ~15°; mirrors
 * public/favicon.svg) — used for the favicon and the hero. `Logo` is the header lockup:
 * SLH's **official wordmark SVG** (public/slh-logo.svg) + an "AI Hub" product tag.
 */

export const SLH_RED = '#FF0000';
export const SLH_ORANGE = '#ef7c00';

/** The Swiss Learning Hub square mark. Size via `size` (px). */
export function SlhMark({ size = 24, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 47 47"
      className={className}
      role="img"
      aria-label="Swiss Learning Hub"
      xmlns="http://www.w3.org/2000/svg"
    >
      <g transform="matrix(0.965926,-0.258819,0.258819,0.965926,-2.59,3.39)">
        <rect x="5.79" y="5.77" width="11.55" height="11.55" fill={SLH_RED} />
      </g>
      <rect x="28.86" y="5.77" width="11.55" height="11.55" fill={SLH_RED} />
      <rect x="5.77" y="28.87" width="11.55" height="11.55" fill={SLH_RED} />
      <rect x="28.85" y="28.87" width="11.55" height="11.55" fill={SLH_RED} />
    </svg>
  );
}

/**
 * Header lockup: SLH's official wordmark + an "AI Hub" product tag, separated by a
 * divider with consistent clear-space. The official wordmark (orange + red) reads on
 * both light and dark backgrounds, so no theme variant is needed.
 */
export function Logo({ className = '' }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <img src="/slh-logo.svg" alt="Swiss Learning Hub" className="h-[18px] w-auto" />
      <span aria-hidden className="h-4 w-px bg-border" />
      <span className="text-sm font-bold tracking-tight">
        <span style={{ color: SLH_ORANGE }}>AI</span> Hub
      </span>
    </span>
  );
}
