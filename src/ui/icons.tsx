import type { ReactNode } from 'react'

export type IconName =
  | 'brush'
  | 'poly'
  | 'rect'
  | 'bucket'
  | 'eraser'
  | 'pick'
  | 'occ'
  | 'cut'
  | 'sparkle'

const D: Record<IconName, ReactNode> = {
  brush: (
    <>
      <path d="M11.2 3.1l1.7 1.7-5.2 5.2-1.7-1.7z" />
      <path d="M6 8.3c-1 .7-1.3 2-1.8 3.5 1.5-.5 2.8-.8 3.5-1.8" />
    </>
  ),
  poly: (
    <>
      <path d="M3.5 11.5L5.5 4l7.5 2-1.5 6.5z" />
      <circle cx="3.5" cy="11.5" r="1.1" />
      <circle cx="5.5" cy="4" r="1.1" />
      <circle cx="13" cy="6" r="1.1" />
      <circle cx="11.5" cy="12.5" r="1.1" />
    </>
  ),
  rect: <rect x="3" y="4" width="10" height="8" rx="0.5" />,
  bucket: (
    <>
      <path d="M3.2 7.4l4.6-4.2 5 4.6-4.6 4.2z" />
      <path d="M12.9 10c-.7 1-1.1 1.6-1.1 2.2a1.1 1.1 0 002.2 0c0-.6-.4-1.2-1.1-2.2z" />
    </>
  ),
  eraser: (
    <>
      <path d="M9.6 3.4l3 3-5.2 5.2h-3l-1.5-1.5z" />
      <path d="M4 12.6h8.5" />
    </>
  ),
  pick: (
    <>
      <path d="M12.9 3.1a1.5 1.5 0 00-2.2 0l-1.3 1.4" />
      <path d="M8.2 4.9l2.9 2.9" />
      <path d="M10.2 5.6l-5.5 5.6-.6 2 2-.6 5.5-5.6" />
    </>
  ),
  occ: (
    <>
      <path d="M3.5 3.5h6v6h-6z" />
      <path d="M6.5 6.5h6v6h-6z" fill="var(--bg)" />
    </>
  ),
  cut: (
    <>
      <circle cx="4.4" cy="11.9" r="1.6" />
      <circle cx="11.6" cy="11.9" r="1.6" />
      <path d="M5.6 10.7L12 3.2" />
      <path d="M10.4 10.7L4 3.2" />
    </>
  ),
  sparkle: <path d="M8 2.4l1.5 3.9 3.9 1.5-3.9 1.5L8 13.2 6.5 9.3 2.6 7.8l3.9-1.5z" />,
}

export function Icon({ name }: { name: IconName }) {
  return (
    <svg
      viewBox="0 0 16 16"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.3"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {D[name]}
    </svg>
  )
}
