import React, { useState } from 'react';

export default function Avatar({ src, handle, size = 40 }) {
  const [errored, setErrored] = useState(false);
  const showImage = src && !errored;
  return (
    <div
      className="rounded-full overflow-hidden shrink-0 flex items-center justify-center font-semibold"
      style={{
        width: size,
        height: size,
        background: 'var(--color-accent-dim)',
        color: 'var(--color-accent)',
        fontSize: size * 0.4,
      }}
    >
      {showImage ? (
        <img
          src={src}
          alt={handle ? `${handle}'s avatar` : 'avatar'}
          className="w-full h-full object-cover"
          referrerPolicy="no-referrer"
          onError={() => setErrored(true)}
        />
      ) : (
        (handle?.[0] || '?').toUpperCase()
      )}
    </div>
  );
}
