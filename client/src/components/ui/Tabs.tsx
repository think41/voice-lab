interface TabsProps<T extends string> {
  value: T;
  options: T[];
  onChange: (value: T) => void;
}

export function Tabs<T extends string>({ value, options, onChange }: TabsProps<T>) {
  return (
    <div className="inline-flex rounded-md border border-line bg-white p-0.5">
      {options.map((option) => (
        <button
          key={option}
          className={`h-7 rounded px-3 text-[11px] font-medium capitalize ${value === option ? 'bg-blue-50 text-primary' : 'text-muted hover:text-text'}`}
          onClick={() => onChange(option)}
        >
          {option}
        </button>
      ))}
    </div>
  );
}
