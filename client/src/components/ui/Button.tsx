import type { ButtonHTMLAttributes, ReactNode } from 'react';

type Variant = 'primary' | 'ghost' | 'outline' | 'danger';

const variants: Record<Variant, string> = {
  primary: 'bg-primary text-white hover:bg-[#1558d6] border-primary',
  ghost: 'bg-white/10 text-white/75 hover:bg-white/15 hover:text-white border-transparent',
  outline: 'bg-white text-muted hover:text-text hover:bg-off border-line',
  danger: 'bg-white text-danger hover:bg-red-50 border-red-200'
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  icon?: ReactNode;
}

export function Button({ variant = 'outline', icon, children, className = '', ...props }: ButtonProps) {
  return (
    <button
      className={`inline-flex h-8 items-center justify-center gap-2 rounded-md border px-3 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`}
      {...props}
    >
      {icon}
      {children}
    </button>
  );
}
