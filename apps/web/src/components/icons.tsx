/**
 * Tiny inline icon set. Every status icon travels with a text label
 * (plan.md section 3: colour never carries meaning alone), so these are
 * decorative and aria-hidden.
 */

interface IconProps {
  className?: string;
}

export function CheckIcon({ className = "h-3.5 w-3.5" }: IconProps) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className={className}>
      <circle cx="8" cy="8" r="6.25" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M5.3 8.3l1.8 1.8 3.6-4.2"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function AlertIcon({ className = "h-3.5 w-3.5" }: IconProps) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className={className}>
      <circle cx="8" cy="8" r="6.25" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 4.8v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="8" cy="11.2" r="0.9" fill="currentColor" />
    </svg>
  );
}

export function PendingIcon({ className = "h-3.5 w-3.5" }: IconProps) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className={className}>
      <circle
        cx="8"
        cy="8"
        r="6.25"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeDasharray="2.6 2.2"
      />
    </svg>
  );
}
