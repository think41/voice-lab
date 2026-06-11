export function Toast({ message }: { message: string | null }) {
  if (!message) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 rounded-md bg-navy px-4 py-2 text-xs font-medium text-white shadow-panel">
      {message}
    </div>
  );
}
