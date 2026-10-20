import type { ComponentProps } from "react";

const paths = {
  overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  forecasts: "M3 19V5 M3 19h18 M6 14l4-5 4 3 6-7",
  models: "M12 3l9 5-9 5-9-5z M3 12l9 5 9-5 M3 16l9 5 9-5",
  experiments: "M9 3h6 M10 3v6l-6 10a1 1 0 001 2h14a1 1 0 001-2L14 9V3 M8 14h8",
  features: "M4 6h16 M4 12h16 M4 18h16 M8 3v6 M16 9v6 M10 15v6",
  settings: "M4 5h16v14H4z M4 10h16 M10 10v9",
  arrow: "M5 12h14 M13 6l6 6-6 6",
  info: "M12 8h.01 M12 11v6 M21 12a9 9 0 11-18 0 9 9 0 0118 0",
  database:
    "M20 6c0 2-4 3-8 3S4 8 4 6s4-3 8-3 8 1 8 3 M4 6v12c0 2 4 3 8 3s8-1 8-3V6 M4 12c0 2 4 3 8 3s8-1 8-3",
  check: "M5 12l4 4L19 6",
} as const;
export type IconName = keyof typeof paths;

/** Small local vector vocabulary; decorative icons never replace visible labels. */
export function Icon({
  name,
  ...props
}: ComponentProps<"svg"> & { name: IconName }): React.JSX.Element {
  return (
    <svg
      aria-hidden="true"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d={paths[name]} />
    </svg>
  );
}
