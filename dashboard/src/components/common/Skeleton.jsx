import React from 'react';
import { cn } from '../../utils/cn';

export default function Skeleton({ className }) {
  return (
    <div
      className={cn('rounded-lg animate-shimmer', className)}
    />
  );
}

export function SkeletonKPICard() {
  return (
    <div className="card p-5 flex flex-col gap-3">
      <Skeleton className="h-4 w-24" />
      <Skeleton className="h-7 w-16" />
    </div>
  );
}
