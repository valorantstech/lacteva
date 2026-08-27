"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

/**
 * The living milk (LACTEVA-MARKETING-002; drops-not-stream and jar-not-pot
 * per owner direction, 2026-08-27).
 *
 * A GLASS MILK JAR — glass, so the milk stays the subject: through the
 * walls you see a real-time 2D-canvas fluid (a spring-damped surface
 * heightfield) fed by discrete milk drops falling through the jar's mouth.
 * Each drop accelerates under gravity, stretches as it falls, and lands
 * with a plop, a ripple ring and a small crown of micro-droplets. The
 * cursor stirs the surface; a tap plops. Everything is drawn from this
 * file; no library, no CDN, no shader.
 *
 * The jar is ONE geometry: the same SVG path strings draw the canvas
 * (via Path2D) and the static fallback SVG, so the two renderings cannot
 * drift. The static composition is the server render — the no-JS page,
 * the reduced-motion page, and the weak-device page; the canvas only
 * fades in after the simulation has proven it can hold a frame rate, and
 * the static drips hide entirely under reduced motion.
 *
 * Purely decorative — the whole figure is aria-hidden; every fact it
 * could express is stated in the hero's text.
 */

// Design space, 420×470. All drawing happens in these coordinates; one
// scale factor maps them onto the actual canvas.
const W = 420;
const H = 470;
const COLS = 96;

// The jar, as two closed paths: the outer silhouette (stroked as glass)
// and the interior (the clip everything liquid lives inside).
const JAR_OUTER_D =
  "M114 118H306Q312 118 312 128V132Q312 140 304 143L296 146V168" +
  "C296 192 324 198 324 232V368C324 412 296 438 246 440H174" +
  "C124 438 96 412 96 368V232C96 198 124 192 124 168V146L116 143" +
  "Q108 140 108 132V128Q108 118 114 118Z";
const JAR_INTERIOR_D =
  "M132 140V170C132 196 104 202 104 238V366C104 404 132 428 178 430H242" +
  "C288 428 316 404 316 366V238C316 202 288 196 288 170V140Z";

const JAR = { cx: 210, surfHalf: 104, bottom: 448 };
const SURFACE_Y = 240; // resting milk line, just under the shoulder
const MAX_DEFLECT = 14;

// The falling milk. Gravity and cadence are tuned calm: a drop roughly
// every second, arriving with weight but never with hurry.
const GRAVITY = 620; // design px/s²
const DROP_START_VY = 60;

// Watchdog: during the first ~2s of simulation, if most frames miss even a
// 30fps budget the device has told us everything — fall back to the board.
const PROBE_FRAMES = 90;
const SLOW_FRAME_MS = 34;
const SLOW_LIMIT = 45;

type Ring = { x: number; r: number; life: number };
type Drop = { x: number; y: number; vy: number; size: number };
type Splash = { x: number; y: number; vx: number; vy: number; r: number; life: number };

function colX(i: number): number {
  return JAR.cx - JAR.surfHalf + (i / (COLS - 1)) * JAR.surfHalf * 2;
}

function colAt(x: number): number {
  const i = Math.round(
    ((x - (JAR.cx - JAR.surfHalf)) / (JAR.surfHalf * 2)) * (COLS - 1),
  );
  return Math.max(2, Math.min(COLS - 3, i));
}

export function HeroMilk({ className }: { className?: string }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) return;

    let ctx: CanvasRenderingContext2D | null = null;
    let reduced: MediaQueryList | null = null;
    try {
      if (typeof window.matchMedia === "function") {
        reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
        if (reduced.matches) return;
      }
      ctx = canvas.getContext("2d");
    } catch {
      return;
    }
    if (!ctx) return;
    const g = ctx;

    const outer = new Path2D(JAR_OUTER_D);
    const interior = new Path2D(JAR_INTERIOR_D);

    // — Simulation state —
    const heights = new Float32Array(COLS);
    const vels = new Float32Array(COLS);
    const rings: Ring[] = [];
    const drops: Drop[] = [];
    const splashes: Splash[] = [];
    let t = 0;
    let raf = 0;
    let running = true;
    let dead = false;
    let frames = 0;
    let slow = 0;
    let last = performance.now();
    let scale = 1;
    let pointerX = -1;
    let lastPointerX = -1;
    let ringCooldown = 0;
    let dropCount = 0;
    let nextDropIn = 0.4; // the first drop arrives quickly, with the entrance

    const die = () => {
      if (dead) return;
      dead = true;
      running = false;
      cancelAnimationFrame(raf);
      wrap.dataset.motion = "static";
    };

    const fit = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = wrap.clientWidth || 1;
      const h = wrap.clientHeight || 1;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      scale = (w / W) * dpr;
    };

    const surfaceAt = (x: number) => {
      const i = colAt(x);
      return SURFACE_Y + heights[i];
    };

    const plop = (x: number, strength: number) => {
      const c = colAt(x);
      vels[c] += strength;
      vels[c - 1] += strength * 0.55;
      vels[c + 1] += strength * 0.55;
      if (rings.length < 7) rings.push({ x, r: 7, life: 1 });
    };

    const step = () => {
      const dt = 1 / 60;

      // The next drop, when its moment comes: through the jar's mouth from
      // a gently wandering spout, sized with a little deterministic variety
      // (no Math.random — the pattern needs no state and never repeats
      // visibly).
      nextDropIn -= dt;
      if (nextDropIn <= 0) {
        dropCount += 1;
        drops.push({
          x: JAR.cx + Math.sin(dropCount * 2.4) * 34 + Math.sin(t * 0.7) * 6,
          y: -24,
          vy: DROP_START_VY,
          size: 9 + 2.5 * Math.sin(dropCount * 1.7),
        });
        // A drop takes ~0.8s to reach the milk; this cadence keeps one in
        // the air almost always without ever reading as rain.
        nextDropIn = 0.72 + 0.26 * Math.sin(dropCount * 2.9);
      }

      // Falling milk: gravity, then the landing — a plop scaled by how hard
      // it arrives, a ring, and a small crown of micro-droplets.
      for (let i = drops.length - 1; i >= 0; i--) {
        const d = drops[i];
        d.vy += GRAVITY * dt;
        d.y += d.vy * dt;
        const surface = surfaceAt(d.x);
        if (d.y + d.size * 0.5 >= surface) {
          plop(d.x, Math.min(2.4, d.vy * 0.0035 * (d.size / 10)));
          for (let s = 0; s < 3; s++) {
            splashes.push({
              x: d.x + (s - 1) * d.size * 0.5,
              y: surface - 2,
              vx: (s - 1) * (30 + d.size * 2),
              vy: -(70 + d.vy * 0.16) - s * 8,
              r: 1.6 + (s === 1 ? 1.2 : 0.6),
              life: 1,
            });
          }
          drops.splice(i, 1);
        }
      }

      // Splash crown: tiny milk beads arcing up and falling home.
      for (let i = splashes.length - 1; i >= 0; i--) {
        const s = splashes[i];
        s.vy += GRAVITY * dt;
        s.x += s.vx * dt;
        s.y += s.vy * dt;
        s.life -= dt * 1.6;
        if (s.life <= 0 || s.y > surfaceAt(s.x) + 6) splashes.splice(i, 1);
      }

      // Cursor: the surface answers sideways motion under the pointer.
      if (pointerX >= 0 && lastPointerX >= 0) {
        const speed = Math.min(Math.abs(pointerX - lastPointerX), 40);
        if (speed > 0.5) {
          const c = colAt(pointerX);
          const amp = Math.min(speed * 0.045, 1.1);
          vels[c] += amp;
          vels[c - 1] += amp * 0.6;
          vels[c + 1] += amp * 0.6;
          if (speed > 12 && ringCooldown <= 0) {
            rings.push({ x: pointerX, r: 10, life: 1 });
            ringCooldown = 24;
          }
        }
      }
      lastPointerX = pointerX;
      ringCooldown -= 1;

      // Milk is never perfectly still: the faintest ambient swell, so the
      // surface breathes between drops.
      for (let i = 1; i < COLS - 1; i++) {
        vels[i] += Math.sin(t * 0.7 + i * 0.55) * 0.002;
      }

      // Spring toward rest + neighbour tension, twice-damped: milk, not water.
      for (let i = 1; i < COLS - 1; i++) {
        const accel =
          0.02 * (heights[i - 1] + heights[i + 1] - 2 * heights[i]) -
          0.014 * heights[i];
        vels[i] = (vels[i] + accel) * 0.972;
      }
      for (let i = 0; i < COLS; i++) {
        heights[i] += vels[i];
        if (heights[i] > MAX_DEFLECT) heights[i] = MAX_DEFLECT;
        if (heights[i] < -MAX_DEFLECT) heights[i] = -MAX_DEFLECT;
      }
      // Spread passes make waves travel instead of standing.
      for (let pass = 0; pass < 2; pass++) {
        for (let i = 1; i < COLS - 1; i++) {
          vels[i - 1] += 0.11 * (heights[i] - heights[i - 1]);
          vels[i + 1] += 0.11 * (heights[i] - heights[i + 1]);
        }
      }
      // The meniscus: milk clings to the glass at the walls.
      for (const i of [0, 1, 2, COLS - 3, COLS - 2, COLS - 1]) {
        heights[i] *= 0.82;
        vels[i] *= 0.82;
      }

      for (let i = rings.length - 1; i >= 0; i--) {
        rings[i].r += 0.85;
        rings[i].life -= 0.012;
        if (rings[i].life <= 0) rings.splice(i, 1);
      }
      t += dt;
    };

    const drawDrop = (d: Drop) => {
      // A falling drop: round belly, tapering tail — and it stretches as it
      // accelerates, the way liquid actually falls.
      const r = d.size;
      const e = 1 + Math.min(d.vy / 900, 0.55);
      g.beginPath();
      g.moveTo(d.x, d.y - r * 1.9 * e);
      g.bezierCurveTo(d.x - r * 0.95, d.y - r * 0.55, d.x - r, d.y + r * 0.4, d.x, d.y + r);
      g.bezierCurveTo(d.x + r, d.y + r * 0.4, d.x + r * 0.95, d.y - r * 0.55, d.x, d.y - r * 1.9 * e);
      g.closePath();
      g.fillStyle = "#FDFBF4";
      g.fill();
      // One small catch of light on the belly.
      g.beginPath();
      g.ellipse(d.x - r * 0.32, d.y - r * 0.1, r * 0.24, r * 0.38, -0.4, 0, Math.PI * 2);
      g.fillStyle = "rgba(255,255,255,0.85)";
      g.fill();
    };

    const draw = () => {
      g.setTransform(scale, 0, 0, scale, 0, 0);
      g.clearRect(0, 0, W, H);

      // 1 — the falling drops, drawn first: above the mouth they are in
      // open air; below it the glass and milk paint over them, so a
      // landing drop sinks under the surface instead of popping away.
      for (const d of drops) drawDrop(d);

      // 2 — everything liquid, inside the glass.
      g.save();
      g.clip(interior);

      // The milk: live surface on top, straight to the jar floor — the
      // interior clip does the walls.
      const left = JAR.cx - JAR.surfHalf;
      const right = JAR.cx + JAR.surfHalf;
      g.beginPath();
      g.moveTo(left - 4, SURFACE_Y + heights[0]);
      for (let i = 0; i < COLS - 1; i++) {
        const x0 = colX(i);
        const x1 = colX(i + 1);
        const y0 = SURFACE_Y + heights[i];
        const y1 = SURFACE_Y + heights[i + 1];
        g.quadraticCurveTo(x0, y0, (x0 + x1) / 2, (y0 + y1) / 2);
      }
      g.lineTo(right + 4, SURFACE_Y + heights[COLS - 1]);
      g.lineTo(right + 8, JAR.bottom);
      g.lineTo(left - 8, JAR.bottom);
      g.closePath();
      const bg = g.createLinearGradient(left, SURFACE_Y - 10, right, JAR.bottom);
      bg.addColorStop(0, "#FFFFFF");
      bg.addColorStop(0.45, "#FDFBF4");
      bg.addColorStop(1, "#E4DEC9");
      g.fillStyle = bg;
      g.fill();

      // Depth at the bottom of the jar — the board's inset green shadow.
      const shade = g.createLinearGradient(0, SURFACE_Y + 80, 0, JAR.bottom);
      shade.addColorStop(0, "rgba(27,94,32,0)");
      shade.addColorStop(1, "rgba(27,94,32,0.10)");
      g.fillStyle = shade;
      g.fillRect(left - 8, SURFACE_Y, JAR.surfHalf * 2 + 16, JAR.bottom - SURFACE_Y);

      // The crest: light catches the moving surface.
      g.beginPath();
      g.moveTo(left, SURFACE_Y + heights[0]);
      for (let i = 1; i < COLS; i++) {
        g.lineTo(colX(i), SURFACE_Y + heights[i]);
      }
      g.strokeStyle = "rgba(255,255,255,0.85)";
      g.lineWidth = 2;
      g.stroke();

      // The warm highlight, upper left of the milk body.
      const hl = g.createRadialGradient(
        JAR.cx - 58, SURFACE_Y + 46, 4,
        JAR.cx - 58, SURFACE_Y + 46, 66,
      );
      hl.addColorStop(0, "rgba(255,255,255,0.9)");
      hl.addColorStop(1, "rgba(255,255,255,0)");
      g.fillStyle = hl;
      g.fillRect(left, SURFACE_Y - 6, JAR.surfHalf * 2, 130);

      // Ripple rings riding the surface (meniscus green, like the board's).
      for (const ring of rings) {
        g.beginPath();
        g.ellipse(ring.x, surfaceAt(ring.x) + 8, ring.r, ring.r * 0.28, 0, 0, Math.PI * 2);
        g.strokeStyle = `rgba(27,94,32,${(0.14 * ring.life).toFixed(3)})`;
        g.lineWidth = 1.6;
        g.stroke();
      }

      // Glass, from the inside: a breath of tint over everything, and two
      // standing reflections down the walls.
      g.fillStyle = "rgba(255,255,255,0.045)";
      g.fillRect(0, 0, W, H);
      g.beginPath();
      g.moveTo(122, 190);
      g.bezierCurveTo(114, 250, 114, 330, 124, 402);
      g.strokeStyle = "rgba(255,255,255,0.22)";
      g.lineWidth = 7;
      g.stroke();
      g.beginPath();
      g.moveTo(298, 212);
      g.bezierCurveTo(305, 262, 305, 330, 297, 384);
      g.strokeStyle = "rgba(255,255,255,0.12)";
      g.lineWidth = 4;
      g.stroke();
      g.restore();

      // 3 — the splash crown, in front of the glass: milk answering milk.
      for (const s of splashes) {
        g.beginPath();
        g.arc(s.x, s.y, s.r * (0.6 + 0.4 * s.life), 0, Math.PI * 2);
        g.fillStyle = `rgba(253,251,244,${(0.9 * s.life).toFixed(3)})`;
        g.fill();
      }

      // 4 — the jar itself: silhouette stroke and the hint of its mouth.
      g.strokeStyle = "rgba(253,251,244,0.55)";
      g.lineWidth = 3;
      g.stroke(outer);
      g.beginPath();
      g.ellipse(JAR.cx, 120, 88, 8, 0, 0, Math.PI * 2);
      g.strokeStyle = "rgba(255,255,255,0.3)";
      g.lineWidth = 2;
      g.stroke();
    };

    const loop = (now: number) => {
      if (!running) return;
      const dt = now - last;
      last = now;
      if (frames < PROBE_FRAMES) {
        frames += 1;
        if (dt > SLOW_FRAME_MS) slow += 1;
        if (frames === PROBE_FRAMES && slow > SLOW_LIMIT) {
          die();
          return;
        }
      }
      // Fixed-step physics, capped so a background tab does not fast-forward.
      const steps = Math.min(Math.max(Math.round(dt / 16.7), 1), 3);
      for (let i = 0; i < steps; i++) step();
      draw();
      raf = requestAnimationFrame(loop);
    };

    const start = () => {
      if (dead || (running === true && raf !== 0)) return;
      running = true;
      last = performance.now();
      raf = requestAnimationFrame(loop);
    };
    const pause = () => {
      running = false;
      cancelAnimationFrame(raf);
      raf = 0;
    };

    const onPointerMove = (e: PointerEvent) => {
      const rect = wrap.getBoundingClientRect();
      pointerX = ((e.clientX - rect.left) / rect.width) * W;
    };
    const onPointerLeave = () => {
      pointerX = -1;
      lastPointerX = -1;
    };
    const onPointerDown = (e: PointerEvent) => {
      const rect = wrap.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * W;
      plop(x, 3);
    };
    const onReduce = () => {
      if (reduced?.matches) die();
    };

    let io: IntersectionObserver | null = null;
    let ro: ResizeObserver | null = null;
    try {
      fit();
      draw();
      wrap.dataset.motion = "live";
      start();

      ro = new ResizeObserver(fit);
      ro.observe(wrap);
      // Off-screen milk earns no frames.
      io = new IntersectionObserver(([entry]) => {
        if (dead) return;
        if (entry.isIntersecting) start();
        else pause();
      });
      io.observe(wrap);
      wrap.addEventListener("pointermove", onPointerMove);
      wrap.addEventListener("pointerdown", onPointerDown);
      wrap.addEventListener("pointerleave", onPointerLeave);
      reduced?.addEventListener("change", onReduce);
    } catch {
      die();
      return;
    }

    return () => {
      pause();
      dead = true;
      io?.disconnect();
      ro?.disconnect();
      wrap.removeEventListener("pointermove", onPointerMove);
      wrap.removeEventListener("pointerdown", onPointerDown);
      wrap.removeEventListener("pointerleave", onPointerLeave);
      reduced?.removeEventListener("change", onReduce);
    };
  }, []);

  return (
    <div
      ref={wrapRef}
      aria-hidden="true"
      data-motion="static"
      className={cn(
        "group relative mx-auto aspect-[420/470] w-full max-w-[420px] touch-pan-y select-none",
        className,
      )}
    >
      {/* Ground shadow — under both renderings. */}
      <div className="absolute bottom-[3%] left-1/2 h-[4.5%] w-[56%] -translate-x-1/2 rounded-full bg-black/30 blur-lg" />

      {/* The static composition: the server render, the no-JS page, and the
          fallback the canvas hands back to — the SAME jar paths the canvas
          draws, still milk with a gentle wave. Three CSS drips fall through
          the mouth; compositor-only, and hidden entirely under reduced
          motion, where calm milk reads better than frozen rain. */}
      <div
        data-hero-static
        className="absolute inset-0 transition-opacity duration-[var(--motion-slow)] group-data-[motion=live]:opacity-0"
      >
        <svg
          data-hero-drip
          viewBox="0 0 24 34"
          className="hero-drip absolute top-[2%] left-[46%] w-[6%]"
        >
          <path d="M12 2C15 11 20 15 20 23a8 8 0 1 1-16 0C4 15 9 11 12 2Z" fill="#FDFBF4" />
        </svg>
        <svg
          data-hero-drip
          viewBox="0 0 24 34"
          className="hero-drip absolute top-[0%] left-[52%] w-[5%]"
          style={{ "--drip-delay": "-0.9s" } as React.CSSProperties}
        >
          <path d="M12 2C15 11 20 15 20 23a8 8 0 1 1-16 0C4 15 9 11 12 2Z" fill="#FDFBF4" />
        </svg>
        <svg
          data-hero-drip
          viewBox="0 0 24 34"
          className="hero-drip absolute top-[3%] left-[43%] w-[4.5%]"
          style={{ "--drip-delay": "-1.8s" } as React.CSSProperties}
        >
          <path d="M12 2C15 11 20 15 20 23a8 8 0 1 1-16 0C4 15 9 11 12 2Z" fill="#FDFBF4" />
        </svg>
        <svg viewBox="0 0 420 470" className="absolute inset-0 size-full">
          <defs>
            <linearGradient id="hero-jar-milk" x1="0.15" y1="0.4" x2="0.85" y2="1">
              <stop offset="0" stopColor="#FFFFFF" />
              <stop offset="0.45" stopColor="#FDFBF4" />
              <stop offset="1" stopColor="#E4DEC9" />
            </linearGradient>
            <radialGradient id="hero-jar-glow" cx="0.38" cy="0.35" r="0.55">
              <stop offset="0" stopColor="#FFFFFF" stopOpacity="0.9" />
              <stop offset="1" stopColor="#FFFFFF" stopOpacity="0" />
            </radialGradient>
            <clipPath id="hero-jar-clip">
              <path d={JAR_INTERIOR_D} />
            </clipPath>
          </defs>
          <g clipPath="url(#hero-jar-clip)">
            <path
              d="M102 241Q156 235 210 240Q266 245 318 240L318 448H102Z"
              fill="url(#hero-jar-milk)"
            />
            <path
              d="M106 241Q156 235 210 240Q266 245 314 240"
              fill="none"
              stroke="rgba(255,255,255,0.85)"
              strokeWidth="2"
            />
            <ellipse cx="152" cy="286" rx="52" ry="40" fill="url(#hero-jar-glow)" />
            <ellipse
              cx="248" cy="262" rx="34" ry="9"
              fill="none" stroke="rgba(27,94,32,0.10)" strokeWidth="2"
            />
            <rect x="96" y="0" width="228" height="470" fill="rgba(255,255,255,0.045)" />
            <path
              d="M122 190C114 250 114 330 124 402"
              fill="none" stroke="rgba(255,255,255,0.22)" strokeWidth="7"
            />
            <path
              d="M298 212C305 262 305 330 297 384"
              fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="4"
            />
          </g>
          <path
            d={JAR_OUTER_D}
            fill="none"
            stroke="rgba(253,251,244,0.55)"
            strokeWidth="3"
          />
          <ellipse
            cx="210" cy="120" rx="88" ry="8"
            fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth="2"
          />
        </svg>
      </div>

      <canvas
        ref={canvasRef}
        className="absolute inset-0 size-full opacity-0 transition-opacity duration-[var(--motion-slow)] group-data-[motion=live]:opacity-100"
      />
    </div>
  );
}
