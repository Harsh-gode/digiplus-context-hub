import { useEffect, useRef, useState } from "react";

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/**
 * Network-of-dots background, like the DigiPlus homepage hero.
 * Dots drift slowly; nearby dots are joined by faint lines, and dots near the cursor light up.
 * Uses a single <canvas> and requestAnimationFrame; stops when unmounted; static if reduced motion is on.
 */
export function ParticleField({ className = "", density = 0.00011 }) {
  const ref = useRef(null);
  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas.getContext("2d");
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let w = 0, h = 0, raf = 0, dots = [];
    const mouse = { x: -999, y: -999 };
    const colors = ["236,92,116", "180,86,196", "91,110,225"];

    const resize = () => {
      const r = canvas.getBoundingClientRect();
      w = r.width; h = r.height;
      canvas.width = w * dpr; canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const n = Math.max(24, Math.round(w * h * density));
      dots = Array.from({ length: n }, () => ({
        x: Math.random() * w, y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.25, vy: (Math.random() - 0.5) * 0.25,
        c: colors[Math.floor(Math.random() * colors.length)],
      }));
    };
    const draw = () => {
      ctx.clearRect(0, 0, w, h);
      for (const d of dots) {
        d.x += d.vx; d.y += d.vy;
        if (d.x < 0 || d.x > w) d.vx *= -1;
        if (d.y < 0 || d.y > h) d.vy *= -1;
      }
      for (let i = 0; i < dots.length; i++) {
        const a = dots.at(i);
        for (let j = i + 1; j < dots.length; j++) {
          const b = dots.at(j);
          const dist = Math.hypot(a.x - b.x, a.y - b.y);
          if (dist < 110) {
            ctx.strokeStyle = `rgba(${a.c},${0.16 * (1 - dist / 110)})`;
            ctx.lineWidth = 0.6;
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          }
        }
        const md = Math.hypot(a.x - mouse.x, a.y - mouse.y);
        const near = md < 140;
        if (near) {
          ctx.strokeStyle = `rgba(${a.c},${0.35 * (1 - md / 140)})`;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(mouse.x, mouse.y); ctx.stroke();
        }
        ctx.fillStyle = `rgba(${a.c},${near ? 0.9 : 0.45})`;
        ctx.beginPath(); ctx.arc(a.x, a.y, near ? 2.2 : 1.5, 0, Math.PI * 2); ctx.fill();
      }
      if (!reducedMotion()) raf = requestAnimationFrame(draw);
    };
    const onMove = (e) => { const r = canvas.getBoundingClientRect(); mouse.x = e.clientX - r.left; mouse.y = e.clientY - r.top; };
    const onLeave = () => { mouse.x = -999; mouse.y = -999; };

    resize(); draw();
    const parent = canvas.parentElement;
    window.addEventListener("resize", resize);
    parent.addEventListener("mousemove", onMove);
    parent.addEventListener("mouseleave", onLeave);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      parent.removeEventListener("mousemove", onMove);
      parent.removeEventListener("mouseleave", onLeave);
    };
  }, [density]);
  return <canvas ref={ref} aria-hidden="true" className={`absolute inset-0 w-full h-full pointer-events-none ${className}`} />;
}

/** Number that counts up from 0 to `value` when it first appears. */
export function CountUp({ value, duration = 700 }) {
  const [n, setN] = useState(reducedMotion() ? value : 0);
  useEffect(() => {
    if (reducedMotion()) { setN(value); return; }
    let raf, start;
    const step = (t) => {
      start ??= t;
      const p = Math.min((t - start) / duration, 1);
      setN(Math.round(value * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);
  return <>{n}</>;
}
