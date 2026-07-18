import React, { useState, useRef, useLayoutEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Info } from 'lucide-react';
import { cn } from '../../utils/cn';

// Small "i" icon that reveals an explanatory tooltip on hover OR keyboard
// focus (tabIndex + onFocus/onBlur, not just :hover -- so this is usable
// without a mouse). Deliberately its own component rather than a native
// `title` attribute: native tooltips are slow to appear, unstyled, and
// don't wrap long explanations legibly.
//
// The tooltip bubble is rendered through a portal into document.body,
// positioned with `fixed` coordinates computed from the trigger's
// getBoundingClientRect(). It used to be an absolutely-positioned sibling
// instead, which any scrollable/overflow-clipped ancestor (a table's
// `overflow-x-auto` wrapper, for one -- CSS quietly turns overflow-y into
// `auto` too whenever overflow-x is non-visible) would clip, cutting the
// bubble off or hiding it outright. Escaping to body sidesteps every such
// ancestor at once instead of special-casing each ancestor.
export default function InfoTip({ text, side = 'top', className }) {
  const [visible, setVisible] = useState(false);
  const [rect, setRect] = useState(null);
  const timeoutRef = useRef(null);
  const btnRef = useRef(null);

  const measure = useCallback(() => {
    const el = btnRef.current;
    if (!el) return;
    setRect(el.getBoundingClientRect());
  }, []);

  const show = () => {
    clearTimeout(timeoutRef.current);
    measure();
    setVisible(true);
  };
  const hide = () => {
    // Tiny delay so a mouse slipping from icon to tooltip (for text
    // selection / re-reading) doesn't instantly dismiss it.
    timeoutRef.current = setTimeout(() => setVisible(false), 80);
  };

  // Keep the bubble glued to its trigger while visible -- the trigger can
  // move under it from page scroll (inc. an ancestor's own internal
  // scroll) or a window resize, since position is computed once on show.
  useLayoutEffect(() => {
    if (!visible) return undefined;
    window.addEventListener('scroll', measure, true);
    window.addEventListener('resize', measure);
    return () => {
      window.removeEventListener('scroll', measure, true);
      window.removeEventListener('resize', measure);
    };
  }, [visible, measure]);

  const bubbleStyle = () => {
    if (!rect) return { display: 'none' };
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    switch (side) {
      case 'bottom':
        return { top: rect.bottom + 8, left: centerX, transform: 'translate(-50%, 0)' };
      case 'left':
        return { top: centerY, left: rect.left - 8, transform: 'translate(-100%, -50%)' };
      case 'right':
        return { top: centerY, left: rect.right + 8, transform: 'translate(0, -50%)' };
      case 'top':
      default:
        return { top: rect.top - 8, left: centerX, transform: 'translate(-50%, -100%)' };
    }
  };

  return (
    <span className={cn('relative inline-flex items-center', className)}>
      <button
        ref={btnRef}
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
      {visible && rect && createPortal(
        <span
          role="tooltip"
          onMouseEnter={show}
          onMouseLeave={hide}
          className="fixed z-[9999] w-[240px] max-w-[70vw] px-3 py-2 rounded-lg text-xs leading-relaxed shadow-lg animate-fade-in"
          style={{
            ...bubbleStyle(),
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-default)',
            color: 'var(--color-text-secondary)',
          }}
        >
          {text}
        </span>,
        document.body,
      )}
    </span>
  );
}
