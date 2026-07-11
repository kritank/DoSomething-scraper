import React from 'react';
import { cn } from '../../utils/cn';

export default function Input({ className, error, ...props }) {
  return (
    <input
      className={cn(
        'w-full px-3.5 py-2.5 rounded-xl text-sm outline-none transition-all',
        'bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)]',
        'border border-[var(--color-border-default)]',
        'placeholder:text-[var(--color-text-muted)]',
        'focus:border-[var(--color-accent)] focus:shadow-[var(--shadow-accent)]',
        error && 'border-[var(--color-danger)]',
        className,
      )}
      {...props}
    />
  );
}
