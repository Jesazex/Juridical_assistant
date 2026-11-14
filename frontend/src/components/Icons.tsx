import type { ReactNode } from "react";

type IconProps = { size?: number };

function Svg({ size = 18, children }: IconProps & { children: ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" fill="none">
      {children}
    </svg>
  );
}

const stroke = {
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function IconPlus(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 5v14M5 12h14" {...stroke} />
    </Svg>
  );
}

export function IconMenu(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 7h16M4 12h16M4 17h12" {...stroke} />
    </Svg>
  );
}

export function IconClose(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 6l12 12M18 6L6 18" {...stroke} />
    </Svg>
  );
}

export function IconTrash(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M5 7h14M9 7V5h6v2M8 7l.7 12h6.6L16 7" {...stroke} />
    </Svg>
  );
}

export function IconPencil(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 20l3.2-.6L19 7.6 16.4 5 4.6 16.8 4 20z" {...stroke} />
    </Svg>
  );
}

export function IconPanel(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="4" y="4" width="16" height="16" rx="2" {...stroke} />
      <path d="M14 4v16" {...stroke} />
    </Svg>
  );
}

export function IconDoc(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M7 3.5h7l4 4V20a1.5 1.5 0 0 1-1.5 1.5h-9.5A1.5 1.5 0 0 1 5.5 20V5A1.5 1.5 0 0 1 7 3.5z" {...stroke} />
      <path d="M14 3.8V8h4.2M8 12h8M8 16h6" {...stroke} />
    </Svg>
  );
}

export function IconSearch(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="11" cy="11" r="6" {...stroke} />
      <path d="M16 16l4 4" {...stroke} />
    </Svg>
  );
}

export function IconRetry(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M19 12a7 7 0 1 1-2-4.9" {...stroke} />
      <path d="M19 5v4.2h-4.2" {...stroke} />
    </Svg>
  );
}

export function BrandMark() {
  return (
    <svg className="brand__mark" viewBox="0 0 36 36" aria-hidden="true">
      <rect width="36" height="36" rx="9" fill="#1c3c5e" />
      <rect x="9" y="8" width="18" height="20" rx="2" fill="#f6f1e8" />
      <path d="M12 14h12M12 18h12M12 22h7" stroke="#9a4e32" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
