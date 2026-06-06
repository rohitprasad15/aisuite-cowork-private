// A small set of clean, single-weight line icons (SF-Symbols-ish): 24px grid, 1.7 stroke,
// currentColor, rounded caps/joins. Replaces emoji in the chrome for a crisp, consistent look.

type IconName =
  | "sparkle"
  | "folder"
  | "folderPlus"
  | "plus"
  | "clock"
  | "sliders"
  | "code"
  | "pencil"
  | "branch";

export function Icon({
  name,
  size = 16,
  className,
}: {
  name: IconName;
  size?: number;
  className?: string;
}) {
  const s = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className,
    "aria-hidden": true,
  };

  switch (name) {
    case "sparkle":
      // Filled 4-point twinkle — crisp at small sizes.
      return (
        <svg {...s} fill="currentColor" stroke="none">
          <path d="M12 2.4c.5 4.7 2.5 6.7 7.2 7.2-4.7.5-6.7 2.5-7.2 7.2-.5-4.7-2.5-6.7-7.2-7.2 4.7-.5 6.7-2.5 7.2-7.2z" />
        </svg>
      );
    case "folder":
      return (
        <svg {...s}>
          <path d="M3 8.6c0-1.1.9-2 2-2h2.7c.5 0 1 .2 1.4.6l.8.8c.4.4.9.6 1.4.6H19c1.1 0 2 .9 2 2V17c0 1.1-.9 2-2 2H5c-1.1 0-2-.9-2-2V8.6z" />
        </svg>
      );
    case "folderPlus":
      return (
        <svg {...s}>
          <path d="M3 8.6c0-1.1.9-2 2-2h2.7c.5 0 1 .2 1.4.6l.8.8c.4.4.9.6 1.4.6H19c1.1 0 2 .9 2 2V17c0 1.1-.9 2-2 2H5c-1.1 0-2-.9-2-2V8.6z" />
          <path d="M12 11.4v4.2M9.9 13.5h4.2" />
        </svg>
      );
    case "plus":
      return (
        <svg {...s}>
          <path d="M12 5.5v13M5.5 12h13" />
        </svg>
      );
    case "clock":
      return (
        <svg {...s}>
          <circle cx="12" cy="12" r="8.3" />
          <path d="M12 7.8V12l2.8 1.7" />
        </svg>
      );
    case "sliders":
      return (
        <svg {...s}>
          <path d="M4 7h16M4 12h16M4 17h16" />
          <circle cx="15.5" cy="7" r="2.4" style={{ fill: "var(--panel)" }} />
          <circle cx="8.5" cy="12" r="2.4" style={{ fill: "var(--panel)" }} />
          <circle cx="14" cy="17" r="2.4" style={{ fill: "var(--panel)" }} />
        </svg>
      );
    case "code":
      return (
        <svg {...s}>
          <path d="M8.5 8.5 4.5 12l4 3.5M15.5 8.5l4 3.5-4 3.5" />
        </svg>
      );
    case "pencil":
      return (
        <svg {...s}>
          <path d="M4 20l1.1-3.9L15.6 5.6a1.6 1.6 0 0 1 2.3 0l.5.5a1.6 1.6 0 0 1 0 2.3L7.9 18.9 4 20z" />
          <path d="M14.5 6.7l2.8 2.8" />
        </svg>
      );
    case "branch":
      return (
        <svg {...s}>
          <circle cx="7" cy="6" r="2.1" />
          <circle cx="7" cy="18" r="2.1" />
          <circle cx="17" cy="8" r="2.1" />
          <path d="M7 8.1v7.8M7 12.5c5.4 0 10-.4 10-2.4" />
        </svg>
      );
  }
}
