import { X } from 'lucide-react';

import { Button } from './Button';

interface ModalProps {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
}

export function Modal({ open, title, subtitle, onClose }: ModalProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy/50">
      <div className="w-[min(420px,90vw)] rounded-xl bg-white p-6 shadow-panel">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-text">{title}</h2>
            {subtitle ? <p className="mt-1 text-xs text-muted">{subtitle}</p> : null}
          </div>
          <button className="rounded-md p-1 text-faint hover:bg-off hover:text-text" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <div className="mt-5 space-y-2">
          <div className="flex items-center justify-between rounded-md bg-off px-3 py-2 text-xs">
            <span>Runtime</span>
            <span className="font-mono text-primary">pipecat-adk</span>
          </div>
          <div className="flex items-center justify-between rounded-md bg-off px-3 py-2 text-xs">
            <span>Session storage</span>
            <span className="font-mono text-primary">Postgres</span>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={onClose}>Deploy draft</Button>
        </div>
      </div>
    </div>
  );
}
