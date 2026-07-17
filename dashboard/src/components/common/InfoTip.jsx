import React, { useState, useRef } from 'react';
import { Info } from 'lucide-react';
import { cn } from '../../utils/cn';

// Small "i" icon that reveals an explanatory tooltip on hover OR keyboard
// focus (tabIndex + onFocus/onBlur, not just :hover -- so this is usable
// without a mouse). Deliberately its own component rather than a native
// `title` attribute: native tooltips are slow to appear, unstyled, and
// don't wrap long explanations legibly.
export default function InfoTip({ text, side = 'top', className }) {
  const [visible, setVisible] = useState(false);
  const timeoutRef = useRef(null);

  const show = () => {
    clearTimeout(timeoutRef.current);
    setVisible(true);
  };
  const hide = () => {
    // Tiny delay so a mouse slipping from icon to tooltip (for text
    // selection / re-reading) doesn't instantly dismiss it.
    timeoutRef.current = setTimeout(() => setVisible(false), 80);
  };

  const sideClasses = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  };

  return (
    <span className={cn('relative inline-flex items-center', className)}>
      <button
        type="button"
        tabIndex={0}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        aria-label={text}
        className="inline-flex items-center justify-center rounded-full outline-none focus-visible:ring-2"
        style={{ color: 'var(--color-text-muted)', ['--tw-ring-color']: 'var(--color-accent)' }}
      >
        <Info className="w-3.5 h-3.5" />
      </button>
      {visible && (
        <span
          role="tooltip"
          onMouseEnter={show}
          onMouseLeave={hide}
          className={cn('absolute z-50 w-[240px] max-w-[70vw] px-3 py-2 rounded-lg text-xs leading-relaxed shadow-lg animate-fade-in', sideClasses[side])}
          style={{
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-default)',
            color: 'var(--color-text-secondary)',
          }}
        >
          {text}
        </span>
      )}
    </span>
  );
}
