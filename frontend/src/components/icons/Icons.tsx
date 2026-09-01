import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function IconBase({ children, ...props }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height="20"
      viewBox="0 0 24 24"
      width="20"
      {...props}
    >
      {children}
    </svg>
  );
}

export function QpMark(props: IconProps) {
  return (
    <svg
      aria-hidden="true"
      className="qp-mark"
      fill="none"
      height="20"
      viewBox="0 0 24 24"
      width="20"
      {...props}
    >
      <rect
        className="svg-draw qp-mark-frame"
        height="17"
        pathLength={1}
        rx="4"
        stroke="currentColor"
        strokeWidth="1.6"
        width="17"
        x="3.5"
        y="3.5"
      />
      <path
        className="svg-draw qp-mark-q"
        d="M8.4 8.4h4.6a2.9 2.9 0 1 1 0 5.8H10.6v2.4"
        pathLength={1}
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.7"
      />
      <path
        className="svg-draw qp-mark-tail"
        d="m13.6 14.1 2.6 2.6"
        pathLength={1}
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.7"
      />
    </svg>
  );
}

export function DrawCheck({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      height="16"
      viewBox="0 0 16 16"
      width="16"
    >
      <circle
        className="svg-draw svg-draw-ring"
        cx="8"
        cy="8"
        pathLength={1}
        r="6.4"
        stroke="currentColor"
        strokeWidth="1.4"
      />
      <path
        className="svg-draw svg-draw-tick"
        d="m5 8.2 2.1 2.1 4.1-4.3"
        pathLength={1}
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
    </svg>
  );
}

export function FileIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M7 3.5h6l4 4V20.5H7z" pathLength={1} stroke="currentColor" strokeWidth="1.6" />
      <path d="M13 3.5v4h4M9.5 12h5M9.5 15h5" pathLength={1} stroke="currentColor" strokeWidth="1.6" />
    </IconBase>
  );
}

export function UploadIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" pathLength={1} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
      <path d="M5 14v5h14v-5" pathLength={1} stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
    </IconBase>
  );
}

export function ChevronIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="m9 6 6 6-6 6" pathLength={1} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
    </IconBase>
  );
}

export function SparkIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 3.5c.5 4.5 2.5 6.5 7 7-4.5.5-6.5 2.5-7 7-.5-4.5-2.5-6.5-7-7 4.5-.5 6.5-2.5 7-7Z" pathLength={1} stroke="currentColor" strokeLinejoin="round" strokeWidth="1.5" />
    </IconBase>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="m5 12.5 4.2 4L19 7" pathLength={1} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
    </IconBase>
  );
}

export function AlertIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 4 3.5 19h17L12 4Z" pathLength={1} stroke="currentColor" strokeLinejoin="round" strokeWidth="1.6" />
      <path d="M12 9v4.5M12 16.5v.1" pathLength={1} stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
    </IconBase>
  );
}

export function SettingsIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" pathLength={1} r="3" stroke="currentColor" strokeWidth="1.6" />
      <path d="M12 3.5v2M12 18.5v2M3.5 12h2M18.5 12h2M6 6l1.4 1.4M16.6 16.6 18 18M18 6l-1.4 1.4M7.4 16.6 6 18" pathLength={1} stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </IconBase>
  );
}

export function DashboardIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect height="6" pathLength={1} rx="1" stroke="currentColor" strokeWidth="1.6" width="6" x="4" y="4" />
      <rect height="6" pathLength={1} rx="1" stroke="currentColor" strokeWidth="1.6" width="6" x="14" y="4" />
      <rect height="6" pathLength={1} rx="1" stroke="currentColor" strokeWidth="1.6" width="6" x="4" y="14" />
      <rect height="6" pathLength={1} rx="1" stroke="currentColor" strokeWidth="1.6" width="6" x="14" y="14" />
    </IconBase>
  );
}

export function ReviewIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M8 5h9.5A1.5 1.5 0 0 1 19 6.5v11a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 5 17.5V8" pathLength={1} stroke="currentColor" strokeWidth="1.6" />
      <path d="m4 5 1.5 1.5L8.5 3.5M9 10h6M9 14h6" pathLength={1} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" />
    </IconBase>
  );
}

export function HistoryIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M5.5 7.5A8 8 0 1 1 4 12" pathLength={1} stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
      <path d="M5.5 3.5v4h4M12 7.5V12l3 2" pathLength={1} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" />
    </IconBase>
  );
}

export function ExitIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M10 5H5v14h5M14 8l4 4-4 4M8 12h10" pathLength={1} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" />
    </IconBase>
  );
}
