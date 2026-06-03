/** Page-level header, tabs, and filters — sticks below the app nav while list content scrolls. */
export default function StickyPageChrome({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="sticky top-[var(--app-header-height,3.25rem)] z-[9] -mx-6 px-6 pt-1 pb-3 mb-2 bg-bg/95 backdrop-blur-sm border-b border-line space-y-3"
    >
      {children}
    </div>
  );
}
