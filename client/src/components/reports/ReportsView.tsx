import { Activity, Clock, DollarSign, Workflow } from 'lucide-react';

const cards = [
  ['Total sessions', '0', Activity],
  ['Avg latency', '0ms', Clock],
  ['Estimated cost', '$0.00', DollarSign],
  ['Handoffs', '0', Workflow]
] as const;

export function ReportsView() {
  return (
    <div className="flex-1 overflow-auto bg-off p-6">
      <div className="mb-5">
        <h1 className="text-lg font-semibold">Reports</h1>
        <p className="mt-1 text-xs text-faint">Operational metrics will populate as test-call traces are recorded.</p>
      </div>
      <div className="grid max-w-5xl grid-cols-4 overflow-hidden rounded-lg border border-line bg-white">
        {cards.map(([label, value, Icon]) => (
          <div key={label} className="border-r border-line p-4 last:border-r-0">
            <Icon className="mb-3 text-primary" size={18} />
            <div className="text-[10px] font-semibold uppercase tracking-wide text-faint">{label}</div>
            <div className="mt-1 font-mono text-2xl font-semibold">{value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
