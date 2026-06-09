export function AudioMeter({ active }: { active: boolean }) {
  return (
    <div className="flex h-10 items-end gap-1">
      {Array.from({ length: 18 }).map((_, index) => (
        <span key={index} className="w-1 rounded-full bg-primary/70 transition-all" style={{ height: active ? `${8 + ((index * 7) % 28)}px` : '6px', opacity: active ? 1 : 0.25 }} />
      ))}
    </div>
  );
}
