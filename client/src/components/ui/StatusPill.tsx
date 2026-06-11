export function StatusPill({ label }: { label: string }) {
  return (
    <div className="inline-flex items-center gap-1.5 rounded-full border border-emerald-300/20 bg-emerald-400/15 px-2.5 py-1 text-[10px] font-semibold text-emerald-300">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-300" />
      {label}
    </div>
  );
}
