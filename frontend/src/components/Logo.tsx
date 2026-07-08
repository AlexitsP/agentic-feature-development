/**
 * SLH AI Hub brand — built around the existing Swiss Learning Hub identity.
 *
 * The mark is SLH's own logo: a 2×2 grid of Swiss-red squares with the top-left one
 * tilted ~15° (reused faithfully from slh-logo-mobile.svg; mirrors public/favicon.svg).
 * The four modules also read as the plug-in apps this hub hosts. The wordmark is
 * "SLH AI Hub" with "AI" in the SLH brand orange.
 */

const SLH_ORANGE = '#ef7c00';

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
        <rect x="5.79" y="5.77" width="11.55" height="11.55" fill="#FF0000" />
      </g>
      <rect x="28.86" y="5.77" width="11.55" height="11.55" fill="#FF0000" />
      <rect x="5.77" y="28.87" width="11.55" height="11.55" fill="#FF0000" />
      <rect x="28.85" y="28.87" width="11.55" height="11.55" fill="#FF0000" />
    </svg>
  );
}

/** Full logo: SLH mark + "SLH AI Hub" wordmark ("AI" in SLH orange). */
export function Logo({ markSize = 22, className = '' }: { markSize?: number; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <SlhMark size={markSize} />
      <span className="font-bold tracking-tight">
        SLH <span style={{ color: SLH_ORANGE }}>AI</span> Hub
      </span>
    </span>
  );
}
