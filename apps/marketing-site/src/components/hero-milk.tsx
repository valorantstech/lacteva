"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

/**
 * The living milk (LACTEVA-MARKETING-002; owner direction 2026-08-27:
 * a dairy milk CAN — the big collection-centre jar — drawn transparent,
 * with a farmer pouring milk in).
 *
 * Three layers, one 420×470 coordinate space, so the whole scene scales
 * as one responsive figure:
 *   1. the canvas — the real-time fluid: a spring-damped surface
 *      heightfield inside the can, fed by milk drops falling from the
 *      farmer's tilted pot; each drop stretches under gravity and lands
 *      with a plop, a ripple ring and a crown of micro-droplets;
 *   2. the static fallback — the same milk, still, plus CSS drips
 *      (hidden under reduced motion: calm milk reads as design, drops
 *      frozen mid-air read as a glitch);
 *   3. the scene layer, always visible — the transparent can (outline,
 *      glass tint, wall reflections, ear handles) and the farmer, drawn
 *      once as SVG over whichever milk is live.
 *
 * The can is ONE geometry: the same path strings clip the canvas fluid
 * (via Path2D) and draw the SVG, so the renderings cannot drift. No
 * library, no CDN, no shader. Purely decorative — the figure is
 * aria-hidden; every fact it could express is stated in the hero's text.
 */

// Design space, 420×470.
const W = 420;
const H = 470;
const COLS = 96;

// The milk can: rolled rim, short neck, shoulder, straight body, bottom
// rim band — the 20L collection-centre can, minus its lid (it is being
// filled). Outer silhouette is stroked as the transparent wall; the
// interior is the clip everything liquid lives inside.
const CAN_OUTER_D =
  "M116 148H244Q250 148 250 154V156Q250 162 244 162H238V190" +
  "C238 206 272 210 272 232V410Q276 414 276 420V424Q276 432 268 432H92" +
  "Q84 432 84 424V420Q84 414 88 410V232" +
  "C88 210 122 206 122 190V162H116Q110 162 110 156V154Q110 148 116 148Z";
const CAN_INTERIOR_D =
  "M128 165V192C128 210 96 214 96 234V414Q96 424 108 424H252" +
  "Q264 424 264 414V234C264 214 232 210 232 192V165Z";
const CAN_HANDLE_R_D = "M272 196C292 194 296 214 282 224L276 216C282 212 282 204 272 204Z";
const CAN_HANDLE_L_D = "M88 196C68 194 64 214 78 224L84 216C78 212 78 204 88 204Z";

const CAN = { cx: 180, surfHalf: 82, bottom: 448 };
const SURFACE_Y = 252; // resting milk line, below the shoulder
const MAX_DEFLECT = 13;

// Where the farmer's pot pours from, and how the milk falls.
const POUR = { x: 216, y: 128 };
const GRAVITY = 620; // design px/s²
const DROP_START_VY = 50;

// Watchdog: during the first ~2s of simulation, if most frames miss even a
// 30fps budget the device has told us everything — fall back to the scene.
const PROBE_FRAMES = 90;
const SLOW_FRAME_MS = 34;
const SLOW_LIMIT = 45;

type Ring = { x: number; r: number; life: number };
type Drop = { x: number; y: number; vy: number; size: number };
type Splash = { x: number; y: number; vx: number; vy: number; r: number; life: number };

function colX(i: number): number {
  return CAN.cx - CAN.surfHalf + (i / (COLS - 1)) * CAN.surfHalf * 2;
}

function colAt(x: number): number {
  const i = Math.round(
    ((x - (CAN.cx - CAN.surfHalf)) / (CAN.surfHalf * 2)) * (COLS - 1),
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

    const interior = new Path2D(CAN_INTERIOR_D);

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
    let nextDropIn = 0.3; // the first drop arrives with the entrance

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
      if (rings.length < 7) rings.push({ x, r: 6, life: 1 });
    };

    const step = () => {
      const dt = 1 / 60;

      // The next drop, from the farmer's pot lip — sized and timed with a
      // little deterministic variety (no Math.random: the pattern needs no
      // state and never repeats visibly). The fall is short, so the
      // cadence is quick enough that one is usually in the air.
      nextDropIn -= dt;
      if (nextDropIn <= 0) {
        dropCount += 1;
        drops.push({
          x: POUR.x + Math.sin(dropCount * 2.4) * 7,
          y: POUR.y,
          vy: DROP_START_VY,
          size: 7.5 + 2 * Math.sin(dropCount * 1.7),
        });
        nextDropIn = 0.55 + 0.2 * Math.sin(dropCount * 2.9);
      }

      // Falling milk: gravity, then the landing — a plop scaled by how hard
      // it arrives, a ring, and a small crown of micro-droplets.
      for (let i = drops.length - 1; i >= 0; i--) {
        const d = drops[i];
        d.vy += GRAVITY * dt;
        d.y += d.vy * dt;
        const surface = surfaceAt(d.x);
        if (d.y + d.size * 0.5 >= surface) {
          plop(d.x, Math.min(2.2, d.vy * 0.004 * (d.size / 9)));
          for (let s = 0; s < 3; s++) {
            splashes.push({
              x: d.x + (s - 1) * d.size * 0.5,
              y: surface - 2,
              vx: (s - 1) * (28 + d.size * 2),
              vy: -(60 + d.vy * 0.16) - s * 8,
              r: 1.4 + (s === 1 ? 1.1 : 0.5),
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
            rings.push({ x: pointerX, r: 9, life: 1 });
            ringCooldown = 24;
          }
        }
      }
      lastPointerX = pointerX;
      ringCooldown -= 1;

      // Milk is never perfectly still: the faintest ambient swell.
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
      // The meniscus: milk clings to the can wall.
      for (const i of [0, 1, 2, COLS - 3, COLS - 2, COLS - 1]) {
        heights[i] *= 0.82;
        vels[i] *= 0.82;
      }

      for (let i = rings.length - 1; i >= 0; i--) {
        rings[i].r += 0.8;
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
      g.beginPath();
      g.ellipse(d.x - r * 0.32, d.y - r * 0.1, r * 0.24, r * 0.38, -0.4, 0, Math.PI * 2);
      g.fillStyle = "rgba(255,255,255,0.85)";
      g.fill();
    };

    const draw = () => {
      g.setTransform(scale, 0, 0, scale, 0, 0);
      g.clearRect(0, 0, W, H);

      // 1 — the falling drops: in open air above the mouth, and the milk
      // paints over them below it, so a landing drop sinks under the
      // surface instead of popping away.
      for (const d of drops) drawDrop(d);

      // 2 — the milk, inside the transparent can. The interior clip does
      // the walls; the scene SVG above supplies the can itself.
      g.save();
      g.clip(interior);

      const left = CAN.cx - CAN.surfHalf;
      const right = CAN.cx + CAN.surfHalf;
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
      g.lineTo(right + 8, CAN.bottom);
      g.lineTo(left - 8, CAN.bottom);
      g.closePath();
      const bg = g.createLinearGradient(left, SURFACE_Y - 10, right, CAN.bottom);
      bg.addColorStop(0, "#FFFFFF");
      bg.addColorStop(0.45, "#FDFBF4");
      bg.addColorStop(1, "#E4DEC9");
      g.fillStyle = bg;
      g.fill();

      // Depth at the bottom of the can.
      const shade = g.createLinearGradient(0, SURFACE_Y + 70, 0, CAN.bottom);
      shade.addColorStop(0, "rgba(27,94,32,0)");
      shade.addColorStop(1, "rgba(27,94,32,0.10)");
      g.fillStyle = shade;
      g.fillRect(left - 8, SURFACE_Y, CAN.surfHalf * 2 + 16, CAN.bottom - SURFACE_Y);

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
        CAN.cx - 46, SURFACE_Y + 44, 4,
        CAN.cx - 46, SURFACE_Y + 44, 60,
      );
      hl.addColorStop(0, "rgba(255,255,255,0.9)");
      hl.addColorStop(1, "rgba(255,255,255,0)");
      g.fillStyle = hl;
      g.fillRect(left, SURFACE_Y - 6, CAN.surfHalf * 2, 120);

      // Ripple rings riding the surface.
      for (const ring of rings) {
        g.beginPath();
        g.ellipse(ring.x, surfaceAt(ring.x) + 7, ring.r, ring.r * 0.28, 0, 0, Math.PI * 2);
        g.strokeStyle = `rgba(27,94,32,${(0.14 * ring.life).toFixed(3)})`;
        g.lineWidth = 1.5;
        g.stroke();
      }
      g.restore();

      // 3 — the splash crown, in front: milk answering milk.
      for (const s of splashes) {
        g.beginPath();
        g.arc(s.x, s.y, s.r * (0.6 + 0.4 * s.life), 0, Math.PI * 2);
        g.fillStyle = `rgba(253,251,244,${(0.9 * s.life).toFixed(3)})`;
        g.fill();
      }
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
      {/* Ground shadow — one for the can, one for the farmer. */}
      <div className="absolute bottom-[5%] left-[13%] h-[4%] w-[50%] rounded-full bg-black/30 blur-lg" />
      <div className="absolute bottom-[5%] right-[6%] h-[3.5%] w-[26%] rounded-full bg-black/25 blur-lg" />

      {/* The static milk: the server render, the no-JS page, and the
          fallback the canvas hands back to. Three CSS drips fall from the
          pot; compositor-only, hidden entirely under reduced motion. */}
      <div
        data-hero-static
        className="absolute inset-0 transition-opacity duration-[var(--motion-slow)] group-data-[motion=live]:opacity-0"
      >
        <svg
          data-hero-drip
          viewBox="0 0 24 34"
          className="hero-drip absolute top-[27%] left-[49%] w-[4.5%]"
        >
          <path d="M12 2C15 11 20 15 20 23a8 8 0 1 1-16 0C4 15 9 11 12 2Z" fill="#FDFBF4" />
        </svg>
        <svg
          data-hero-drip
          viewBox="0 0 24 34"
          className="hero-drip absolute top-[26%] left-[52%] w-[4%]"
          style={{ "--drip-delay": "-0.9s" } as React.CSSProperties}
        >
          <path d="M12 2C15 11 20 15 20 23a8 8 0 1 1-16 0C4 15 9 11 12 2Z" fill="#FDFBF4" />
        </svg>
        <svg
          data-hero-drip
          viewBox="0 0 24 34"
          className="hero-drip absolute top-[28%] left-[46.5%] w-[3.5%]"
          style={{ "--drip-delay": "-1.8s" } as React.CSSProperties}
        >
          <path d="M12 2C15 11 20 15 20 23a8 8 0 1 1-16 0C4 15 9 11 12 2Z" fill="#FDFBF4" />
        </svg>
        <svg viewBox="0 0 420 470" className="absolute inset-0 size-full">
          <defs>
            <linearGradient id="hero-can-milk" x1="0.15" y1="0.4" x2="0.85" y2="1">
              <stop offset="0" stopColor="#FFFFFF" />
              <stop offset="0.45" stopColor="#FDFBF4" />
              <stop offset="1" stopColor="#E4DEC9" />
            </linearGradient>
            <radialGradient id="hero-can-glow" cx="0.38" cy="0.35" r="0.55">
              <stop offset="0" stopColor="#FFFFFF" stopOpacity="0.9" />
              <stop offset="1" stopColor="#FFFFFF" stopOpacity="0" />
            </radialGradient>
            <clipPath id="hero-can-clip">
              <path d={CAN_INTERIOR_D} />
            </clipPath>
          </defs>
          <g clipPath="url(#hero-can-clip)">
            <path
              d="M94 253Q136 248 180 252Q226 257 266 252L266 448H94Z"
              fill="url(#hero-can-milk)"
            />
            <path
              d="M96 253Q136 248 180 252Q226 257 264 252"
              fill="none"
              stroke="rgba(255,255,255,0.85)"
              strokeWidth="2"
            />
            <ellipse cx="134" cy="296" rx="46" ry="36" fill="url(#hero-can-glow)" />
            <ellipse
              cx="214" cy="272" rx="30" ry="8"
              fill="none" stroke="rgba(27,94,32,0.10)" strokeWidth="2"
            />
          </g>
        </svg>
      </div>

      <canvas
        ref={canvasRef}
        className="absolute inset-0 size-full opacity-0 transition-opacity duration-[var(--motion-slow)] group-data-[motion=live]:opacity-100"
      />

      {/* The scene layer, always visible over whichever milk is live: the
          transparent can, and the farmer pouring from a small pot. */}
      <svg viewBox="0 0 420 470" className="pointer-events-none absolute inset-0 size-full">
        {/* — The can: glass tint, wall reflections, silhouette, handles. — */}
        <g clipPath="url(#hero-can-scene-clip)">
          <rect x="84" y="140" width="200" height="300" fill="rgba(255,255,255,0.05)" />
          <path
            d="M112 214C104 262 104 336 112 408"
            fill="none" stroke="rgba(255,255,255,0.22)" strokeWidth="6"
          />
          <path
            d="M250 226C256 268 256 336 249 396"
            fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="4"
          />
        </g>
        <defs>
          <clipPath id="hero-can-scene-clip">
            <path d={CAN_INTERIOR_D} />
          </clipPath>
        </defs>
        <path d={CAN_OUTER_D} fill="none" stroke="rgba(253,251,244,0.6)" strokeWidth="3" />
        <path d={CAN_HANDLE_R_D} fill="rgba(253,251,244,0.6)" />
        <path d={CAN_HANDLE_L_D} fill="rgba(253,251,244,0.6)" />
        <ellipse
          cx="180" cy="150" rx="62" ry="6"
          fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth="2"
        />

        {/* — The farmer: flat and friendly, in the brand's creams and
              greens; leaning in, both hands tipping a small pot whose lip
              is where every drop is born (POUR). — */}
        <g>
          {/* legs / lower garment — feet on the can's ground line */}
          <path
            d="M324 268L318 424H342L348 306H358L362 424H386L382 268Z"
            fill="#C9D8BE"
          />
          <ellipse cx="330" cy="427" rx="13" ry="5" fill="#9DAB99" />
          <ellipse cx="374" cy="427" rx="13" ry="5" fill="#9DAB99" />
          {/* kurta */}
          <path
            d="M336 134C322 142 318 170 318 198L316 272Q353 282 388 272L386 198C386 170 380 142 368 134Q352 127 336 134Z"
            fill="#F1EDDD"
          />
          {/* head + turban */}
          <circle cx="352" cy="112" r="13" fill="#E0C39C" />
          <path
            d="M336 108C336 96 344 90 352 90C362 90 368 97 368 108Q352 100 336 108Z"
            fill="#7FD495"
          />
          <circle cx="338" cy="97" r="4.5" fill="#7FD495" />
          {/* arms reaching to the pot */}
          <path
            d="M332 146C304 150 272 142 250 132L246 144C268 154 300 162 330 160Z"
            fill="#F1EDDD"
          />
          <path
            d="M364 150C336 160 300 160 274 152L270 163C298 172 340 170 366 162Z"
            fill="#F1EDDD"
          />
          <circle cx="249" cy="139" r="6" fill="#E0C39C" />
          <circle cx="273" cy="158" r="6" fill="#E0C39C" />
          {/* the small pot, tipped toward the can's mouth */}
          <g transform="rotate(-34 244 128)">
            <rect
              x="228" y="112" width="34" height="28" rx="5"
              fill="rgba(253,251,244,0.14)"
              stroke="rgba(253,251,244,0.85)" strokeWidth="2.5"
            />
            <line
              x1="228" y1="118" x2="262" y2="118"
              stroke="rgba(253,251,244,0.5)" strokeWidth="1.5"
            />
          </g>
          {/* milk at the pot's lip — where every drop is born */}
          <ellipse cx="221" cy="129" rx="6" ry="3.4" fill="#FDFBF4" />
        </g>
      </svg>
    </div>
  );
}
