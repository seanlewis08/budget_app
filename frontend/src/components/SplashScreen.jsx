import React, { useEffect, useRef } from 'react'

export default function SplashScreen({ onContinue }) {
  const splashRef = useRef(null)

  useEffect(() => {
    // Create floating particles
    const splash = splashRef.current
    if (!splash) return
    for (let i = 0; i < 20; i++) {
      const p = document.createElement('div')
      p.className = 'splash-particle'
      p.style.left = Math.random() * 100 + '%'
      p.style.animationDuration = (8 + Math.random() * 12) + 's'
      p.style.animationDelay = (Math.random() * 8) + 's'
      const size = (1 + Math.random() * 2) + 'px'
      p.style.width = size
      p.style.height = size
      splash.appendChild(p)
    }
  }, [])

  return (
    <div className="splash-screen" ref={splashRef}>
      <div className="splash-text">
        <span className="splash-line splash-line1">
          <span className="splash-word">Your</span>&nbsp;
          <span className="splash-word">Finances,</span>
        </span>
        <span className="splash-line splash-line2">
          <span className="splash-word splash-word-teal">Your</span>&nbsp;
          <span className="splash-word splash-word-teal">Machine.</span>
        </span>
      </div>
      <div className="splash-cta">
        <button className="splash-btn" onClick={onContinue}>Continue</button>
      </div>
    </div>
  )
}
