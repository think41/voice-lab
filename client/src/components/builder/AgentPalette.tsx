export function AgentPalette() {
  return (
    <div className="border-t border-line p-3">
      <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-faint">Drag to canvas</div>
      {[['bg-primary', 'Root agent'], ['bg-purple', 'Sub-agent'], ['bg-warning', 'Tool agent']].map(([dot, label]) => (
        <div key={label} className="mb-1.5 flex cursor-grab items-center gap-2 rounded-md border border-line bg-off px-2.5 py-2 text-[11px] font-medium text-muted hover:border-primary hover:bg-blue-50 hover:text-primary">
          <span className={`h-2 w-2 rounded-full ${dot}`} />
          {label}
        </div>
      ))}
    </div>
  );
}
