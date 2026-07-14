
export function MetricCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="border-r border-line bg-white px-4 py-3 last:border-r-0">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-faint">{label}</div>
      <div className="mt-1 font-mono text-xl font-semibold text-text">{value}</div>
      <div className="mt-0.5 text-[10px] text-faint">{sub}</div>
    </div>
  );
}
