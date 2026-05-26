export default function ListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="card divide-y divide-line overflow-hidden animate-pulse">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="p-4">
          <div className="flex items-start gap-3">
            <div className="w-4 h-4 rounded bg-bg-panel" />
            <div className="flex-1 min-w-0">
              <div className="h-4 w-full bg-bg-panel rounded mb-2" />
              <div className="h-3 w-2/3 bg-bg-panel/70 rounded mb-3" />
              <div className="flex gap-2">
                <div className="h-4 w-16 bg-bg-panel rounded-full" />
                <div className="h-4 w-20 bg-bg-panel rounded-full" />
                <div className="h-4 w-14 bg-bg-panel rounded-full" />
              </div>
            </div>
            <div className="flex flex-col items-end gap-1 shrink-0">
              <div className="h-5 w-16 bg-bg-panel rounded-full" />
              <div className="h-1.5 w-28 bg-bg-panel rounded-full" />
              <div className="h-5 w-20 bg-bg-panel rounded-full" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
