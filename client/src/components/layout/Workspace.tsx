import type { ReactNode } from 'react';

export function Workspace({ children }: { children: ReactNode }) {
  return <main className="flex h-[calc(100vh-52px)] overflow-hidden">{children}</main>;
}
