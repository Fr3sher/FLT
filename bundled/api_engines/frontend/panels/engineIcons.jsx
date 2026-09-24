/* The two drawn pictograms of the API engine cards (Nano Banana uses the 🍌
   glyph). currentColor, so the card's accent colours them. */

/** Minimal ChatGPT pictogram — hexagonal knot silhouette. */
export function ChatGptIcon({ className }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true" focusable="false">
      {[0, 60, 120, 180, 240, 300].map((a) => (
        <path key={a} transform={`rotate(${a} 16 16)`}
          d="M16 4.5 a 6.2 6.2 0 0 1 6.2 6.2 v 4 l -3.4 -2 v -2 a 2.8 2.8 0 0 0 -2.8 -2.8 z"
          fill="currentColor" />
      ))}
      <circle cx="16" cy="16" r="3.1" fill="none" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  )
}

/** Routing pictogram for the OpenRouter card: one input fanning out to several
 *  providers — which is exactly what the engine does (one key, many models). */
export function RouterIcon({ className }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true" focusable="false">
      <g stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round">
        <line x1="9" y1="16" x2="17" y2="16" />
        <path d="M17 16 C 21 16, 21 8, 25 8" />
        <path d="M17 16 C 21 16, 21 24, 25 24" />
      </g>
      <circle cx="7" cy="16" r="3" fill="currentColor" />
      <circle cx="25" cy="8" r="2.4" fill="currentColor" opacity="0.85" />
      <circle cx="25" cy="16" r="2.4" fill="currentColor" opacity="0.85" />
      <circle cx="25" cy="24" r="2.4" fill="currentColor" opacity="0.85" />
    </svg>
  )
}
