// Purely decorative background art -- an abstract gradient
// mountain/wave silhouette with a few soft "floating" glow orbs, hand-drawn
// as SVG rather than a photographic image (no image-generation tool is
// available in this environment). aria-hidden since it conveys no
// information; the floating drift animation respects
// prefers-reduced-motion (see global.css).
//
// "hero" is the more prominent version used behind the Overview page's
// hero panel; "ambient" is a much lower-opacity pair of orbs meant to sit
// behind ordinary page content across the app without competing with it.
interface Props {
  variant?: "hero" | "ambient";
}

export function FloatingBackdrop({ variant = "hero" }: Props) {
  const gradientId = `backdrop-${variant}`;

  if (variant === "ambient") {
    return (
      <svg
        className="floating-backdrop floating-backdrop--ambient"
        viewBox="0 0 1200 800"
        preserveAspectRatio="xMidYMid slice"
        aria-hidden="true"
      >
        <defs>
          <radialGradient id={`${gradientId}-a`} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#2563eb" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#2563eb" stopOpacity="0" />
          </radialGradient>
          <radialGradient id={`${gradientId}-b`} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#0d9488" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#0d9488" stopOpacity="0" />
          </radialGradient>
        </defs>
        <circle className="floating-backdrop__orb floating-backdrop__orb--slow" cx="140" cy="120" r="260" fill={`url(#${gradientId}-a)`} />
        <circle className="floating-backdrop__orb floating-backdrop__orb--fast" cx="1080" cy="700" r="320" fill={`url(#${gradientId}-b)`} />
      </svg>
    );
  }

  return (
    <svg
      className="floating-backdrop floating-backdrop--hero"
      viewBox="0 0 600 400"
      preserveAspectRatio="xMidYMax slice"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={`${gradientId}-back`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#2563eb" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#1e3a5f" stopOpacity="0.55" />
        </linearGradient>
        <linearGradient id={`${gradientId}-mid`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#0d9488" stopOpacity="0.45" />
          <stop offset="100%" stopColor="#0b1526" stopOpacity="0.45" />
        </linearGradient>
        <radialGradient id={`${gradientId}-orb`} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Back mountain range */}
      <path
        d="M0 260 L70 190 L150 240 L230 150 L320 230 L400 170 L480 235 L600 180 L600 400 L0 400 Z"
        fill={`url(#${gradientId}-back)`}
      />
      {/* Front mountain range */}
      <path
        d="M0 320 L90 250 L180 300 L260 220 L340 290 L430 235 L520 295 L600 250 L600 400 L0 400 Z"
        fill={`url(#${gradientId}-mid)`}
      />

      <circle className="floating-backdrop__orb floating-backdrop__orb--slow" cx="470" cy="90" r="70" fill={`url(#${gradientId}-orb)`} />
      <circle className="floating-backdrop__orb floating-backdrop__orb--fast" cx="120" cy="70" r="46" fill={`url(#${gradientId}-orb)`} />
      <circle className="floating-backdrop__orb floating-backdrop__orb--slow" cx="270" cy="55" r="30" fill={`url(#${gradientId}-orb)`} />
    </svg>
  );
}
