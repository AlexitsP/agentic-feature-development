/**
 * AlpacAI brand — a cute AI-alpaca mark + wordmark. The mark is a self-contained
 * SVG (fixed brand colors, theme-independent, mirrors public/favicon.svg) so it reads
 * on both light and dark backgrounds; the wordmark uses the theme foreground with the
 * "AI" accented in brand indigo. Swiss-red scarf keeps the Swiss nod.
 */

const INDIGO = '#6C5CE7';

/** The alpaca mark on its rounded brand tile. Size via `size` (px). */
export function AlpacaMark({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      className={className}
      role="img"
      aria-label="AlpacAI"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id="alpacaiBg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#7C6CF5" />
          <stop offset="1" stopColor="#5B4BD6" />
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="64" height="64" rx="15" fill="url(#alpacaiBg)" />
      <path d="M50 12 l1.6 4 4 1.6 -4 1.6 -1.6 4 -1.6 -4 -4 -1.6 4 -1.6 z" fill="#FFD24B" />
      <path d="M23 15 C21 8 25 6 27 12 C28 16 26 20 24 20 Z" fill="#F4E8D5" />
      <path d="M41 15 C43 8 39 6 37 12 C36 16 38 20 40 20 Z" fill="#F4E8D5" />
      <path d="M26 13 C26 6 38 6 38 13 C42 12 42 18 38 18 L26 18 C22 18 22 12 26 13 Z" fill="#FBF3E6" />
      <ellipse cx="32" cy="34" rx="14" ry="17" fill="#F4E8D5" />
      <ellipse cx="32" cy="43" rx="8.5" ry="7.5" fill="#FBF3E6" />
      <circle cx="26" cy="32" r="3.2" fill="#3A3540" />
      <circle cx="38" cy="32" r="3.2" fill="#3A3540" />
      <circle cx="27.1" cy="30.9" r="1" fill="#fff" />
      <circle cx="39.1" cy="30.9" r="1" fill="#fff" />
      <path d="M30 41 h4 a1 1 0 0 1 -4 0 Z" fill="#B98A6B" />
      <path
        d="M32 42 C30 46 28 45 27.5 43.5 M32 42 C34 46 36 45 36.5 43.5"
        fill="none"
        stroke="#C89A78"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
      <path d="M20 51 q12 6 24 0 l0 4 q-12 6 -24 0 Z" fill="#E1000F" />
      <path d="M31 53.6 h2 v1.4 h1.4 v2 h-1.4 v1.4 h-2 v-1.4 h-1.4 v-2 h1.4 z" fill="#fff" />
    </svg>
  );
}

/** Full logo: mark + "AlpacAI" wordmark (AI in brand indigo). */
export function Logo({ markSize = 26, className = '' }: { markSize?: number; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <AlpacaMark size={markSize} />
      <span className="font-bold tracking-tight">
        Alpac<span style={{ color: INDIGO }}>AI</span>
      </span>
    </span>
  );
}
