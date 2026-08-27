import { MARK_PATH } from "@/components/logo";

/**
 * The illustrated lifecycle (LACTEVA-MARKETING-005): six scenes, one per
 * stage — Capture · Manage · Deliver · Bill · Collect · Understand —
 * drawn inline in the hero farmer's flat style: the same skin tones,
 * creams and brand greens, the same friendly geometry. Drawn, not
 * stocked; no external asset, no library.
 *
 * Shared language lives in the primitives below (the villager figure,
 * the mini milk can, the palette), so a new scene is composition rather
 * than reinvention. The indigo accent appears in exactly one place — the
 * Understand scene's computed signal — because the DS reserves that hue
 * for intelligence, and spending it on decoration would spend the one
 * colour that means "the platform noticed something".
 *
 * Every scene is decorative (aria-hidden): the copy beside it carries
 * the facts.
 */

export const SCENE = {
  panel: "#EEF3E8",
  ground: "#D9E3CE",
  skin: "#C98A5B",
  skinShade: "#B87C4F",
  cream: "#F5F1E3",
  cream2: "#F1EDDD",
  creamShade: "#E3DCC4",
  sage: "#C9D8BE",
  green: "#7FD495",
  dairy: "#1B5E20",
  ink: "#3E2C1E",
  steel: "#D9D9D1",
  steelEdge: "#BFBFB5",
  milk: "#FDFBF4",
  paper: "#FFFFFF",
  /** The intelligence accent — computed signals ONLY. */
  indigo: "#5B5BD6",
} as const;

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 260 170"
      aria-hidden="true"
      className="h-auto w-full select-none"
    >
      <rect width="260" height="170" rx="14" fill={SCENE.panel} />
      <line x1="18" y1="141" x2="242" y2="141" stroke={SCENE.ground} strokeWidth="2" />
      {children}
    </svg>
  );
}

/**
 * The shared villager figure — the hero farmer's language at scene
 * scale: turbaned, capped, or with a bun; kurta over trousers; sandals.
 * Arms are per-scene (a gesture is the scene), so none are drawn here.
 */
function Villager({
  x,
  y,
  variant = "turban",
  dress = SCENE.cream,
  legs = "#FAF7EA",
  flip = false,
}: {
  x: number;
  /** y of the ground under the feet. */
  y: number;
  variant?: "turban" | "cap" | "bun";
  dress?: string;
  legs?: string;
  flip?: boolean;
}) {
  return (
    <g transform={`translate(${x} ${y})${flip ? " scale(-1 1)" : ""}`}>
      {/* legs + feet */}
      <path d="M-7 -26L-8 -2H-2L-1 -22H1L2 -2H8L7 -26Z" fill={legs} />
      <ellipse cx="-4.5" cy="-1" rx="4.5" ry="2" fill={SCENE.skin} />
      <ellipse cx="4.5" cy="-1" rx="4.5" ry="2" fill={SCENE.skin} />
      <path d="M-9 1H0M1 1H10" stroke="#6B4A2F" strokeWidth="1.6" strokeLinecap="round" />
      {/* kurta */}
      <path
        d="M-8 -52Q0 -56 8 -52L10 -24Q0 -21 -10 -24Z"
        fill={dress}
      />
      {/* neck + head */}
      <rect x="-2.5" y="-58" width="5" height="5" fill={SCENE.skin} />
      <circle cx="0" cy="-62" r="6.5" fill={SCENE.skin} />
      {variant === "turban" ? (
        <>
          <ellipse cx="0" cy="-67" rx="8.5" ry="4.6" fill={SCENE.cream2} />
          <circle cx="-5" cy="-70" r="2.6" fill={SCENE.cream2} />
        </>
      ) : null}
      {variant === "cap" ? (
        <path d="M-6.5 -66Q0 -72 6.5 -66L6.5 -64H-6.5Z" fill={SCENE.green} />
      ) : null}
      {variant === "bun" ? (
        <>
          <path d="M-6.5 -64Q0 -70 6.5 -64L6.5 -60Q0 -64 -6.5 -60Z" fill={SCENE.ink} />
          <circle cx="6" cy="-68" r="2.8" fill={SCENE.ink} />
        </>
      ) : null}
      {/* the face reads at this size as two eyes and warmth */}
      <circle cx="-2.2" cy="-62" r="0.9" fill={SCENE.ink} />
      <circle cx="2.2" cy="-62" r="0.9" fill={SCENE.ink} />
    </g>
  );
}

/** The mini milk can — the hero's vessel, at prop scale. */
function MilkCan({ x, y, h = 26 }: { x: number; y: number; h?: number }) {
  const w = h * 0.72;
  return (
    <g transform={`translate(${x} ${y}) scale(${h / 26})`}>
      <path
        d={`M${-w / 2 + 2} -22H${w / 2 - 2}L${w / 2} -18Q${w / 2 + 2.5} -17 ${w / 2 + 2.5} -12V-3Q${w / 2 + 2.5} 0 ${w / 2 - 1} 0H${-w / 2 + 1}Q${-w / 2 - 2.5} 0 ${-w / 2 - 2.5} -3V-12Q${-w / 2 - 2.5} -17 ${-w / 2} -18Z`}
        fill={SCENE.steel}
        stroke={SCENE.steelEdge}
        strokeWidth="1"
      />
      <rect x={-w / 2 + 1} y="-25" width={w - 2} height="3.5" rx="1.5" fill={SCENE.steel} stroke={SCENE.steelEdge} strokeWidth="1" />
      <path d={`M${-w / 2 + 3} -14Q${-w / 2 + 1.5} -8 ${-w / 2 + 3.5} -3`} stroke="rgba(255,255,255,0.8)" strokeWidth="1.6" fill="none" />
    </g>
  );
}

/** 1 · CAPTURE — the operator at the scale, the farmer at the counter. */
export function SceneCapture() {
  return (
    <Frame>
      {/* the counter */}
      <rect x="92" y="100" width="96" height="6" rx="3" fill={SCENE.creamShade} />
      <rect x="98" y="106" width="5" height="35" fill={SCENE.creamShade} />
      <rect x="177" y="106" width="5" height="35" fill={SCENE.creamShade} />
      {/* the scale: platform, post, dial */}
      <rect x="112" y="92" width="40" height="8" rx="3" fill={SCENE.steel} stroke={SCENE.steelEdge} strokeWidth="1" />
      <rect x="129" y="58" width="6" height="34" fill={SCENE.steel} stroke={SCENE.steelEdge} strokeWidth="1" />
      <circle cx="132" cy="46" r="13" fill={SCENE.paper} stroke={SCENE.steelEdge} strokeWidth="1.5" />
      <path d="M132 46L138 39" stroke={SCENE.dairy} strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="132" cy="46" r="1.8" fill={SCENE.dairy} />
      <path d="M124 40L126 42M132 36V39M140 40L138 42" stroke={SCENE.steelEdge} strokeWidth="1.2" strokeLinecap="round" />
      {/* the can being weighed */}
      <MilkCan x={158} y={100} h={22} />
      {/* the farmer, bringing the next can */}
      <Villager x={52} y={140} variant="turban" />
      {/* farmer's arm to his can */}
      <path d="M58 96Q66 104 72 112" stroke={SCENE.cream} strokeWidth="5" strokeLinecap="round" fill="none" />
      <circle cx="73" cy="113" r="3.2" fill={SCENE.skin} />
      <MilkCan x={76} y={140} h={24} />
      {/* the operator, reading the entry into the platform */}
      <Villager x={216} y={140} variant="cap" dress={SCENE.sage} />
      <path d="M209 96Q200 100 196 106" stroke={SCENE.sage} strokeWidth="5" strokeLinecap="round" fill="none" />
      <rect x="188" y="102" width="13" height="18" rx="2" transform="rotate(-14 194 111)" fill={SCENE.paper} stroke={SCENE.dairy} strokeWidth="1.2" />
      <circle cx="196" cy="107" r="3" fill={SCENE.skin} />
    </Frame>
  );
}

/** 2 · MANAGE — the organization as people with responsibilities. */
export function SceneManage() {
  return (
    <Frame>
      {/* the manager, clipboard in hand */}
      <Villager x={56} y={140} variant="turban" dress={SCENE.cream} />
      <path d="M63 92Q72 96 78 102" stroke={SCENE.cream} strokeWidth="5" strokeLinecap="round" fill="none" />
      <rect x="72" y="94" width="18" height="24" rx="2" fill={SCENE.paper} stroke={SCENE.creamShade} strokeWidth="1.2" />
      <rect x="77" y="91" width="8" height="5" rx="1.5" fill={SCENE.steel} />
      <path d="M76 102H86M76 107H86M76 112H82" stroke={SCENE.creamShade} strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="79" cy="103" r="3" fill={SCENE.skin} />
      {/* three roles, each its own card: a person, their permissions */}
      {[38, 76, 114].map((y, i) => (
        <g key={y}>
          <rect x="128" y={y} width="104" height="30" rx="7" fill={SCENE.paper} stroke={SCENE.creamShade} strokeWidth="1.2" />
          <circle cx="143" cy={y + 15} r="7" fill={[SCENE.green, SCENE.sage, SCENE.cream2][i]} />
          <circle cx="143" cy={y + 13} r="2.6" fill={SCENE.skin} />
          <path d={`M138 ${y + 20}Q143 ${y + 16.5} 148 ${y + 20}`} fill={SCENE.skin} />
          <rect x="156" y={y + 9} width="46" height="4" rx="2" fill={SCENE.creamShade} />
          <rect x="156" y={y + 17} width="30" height="4" rx="2" fill={SCENE.panel} />
          {/* the grant: what this role may do */}
          <circle cx="218" cy={y + 15} r="6" fill={SCENE.green} opacity="0.35" />
          <path d={`M215 ${y + 15}L217.5 ${y + 17.5}L221.5 ${y + 12.5}`} stroke={SCENE.dairy} strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </g>
      ))}
    </Frame>
  );
}

/** 3 · DELIVER — the van on its round. */
export function SceneDeliver() {
  return (
    <Frame>
      {/* a doorstep to deliver to */}
      <rect x="206" y="70" width="34" height="71" fill={SCENE.cream2} />
      <rect x="212" y="82" width="22" height="52" rx="2" fill={SCENE.creamShade} />
      <circle cx="230" cy="108" r="1.8" fill={SCENE.ink} />
      <path d="M202 70H244" stroke={SCENE.creamShade} strokeWidth="4" strokeLinecap="round" />
      {/* the crate waiting on the step */}
      <rect x="182" y="128" width="18" height="12" rx="2" fill={SCENE.sage} />
      <path d="M186 128V124H190V128M192 128V124H196V128" stroke={SCENE.milk} strokeWidth="2.4" />
      {/* the van */}
      <g>
        <rect x="36" y="76" width="88" height="50" rx="7" fill={SCENE.cream} stroke={SCENE.creamShade} strokeWidth="1.2" />
        <path d="M124 90H144Q152 90 156 100L160 112Q161 126 150 126H124Z" fill={SCENE.cream} stroke={SCENE.creamShade} strokeWidth="1.2" />
        <path d="M128 94H143Q148 94 151 101L154 108H128Z" fill={SCENE.sage} />
        {/* the mark rides the side of the van */}
        <g transform="translate(62 84) scale(0.62)">
          <path d={MARK_PATH} fill={SCENE.dairy} />
        </g>
        <path d="M96 100V120M44 120H116" stroke={SCENE.creamShade} strokeWidth="1.2" />
        <circle cx="62" cy="128" r="10" fill="#3A4A3C" />
        <circle cx="62" cy="128" r="4" fill={SCENE.sage} />
        <circle cx="136" cy="128" r="10" fill="#3A4A3C" />
        <circle cx="136" cy="128" r="4" fill={SCENE.sage} />
      </g>
      {/* moving: the road, and the air it just passed through */}
      <path d="M16 96H28M10 106H26M16 116H30" stroke={SCENE.ground} strokeWidth="2.5" strokeLinecap="round" />
      <path d="M46 146H70M84 146H96M110 146H140" stroke={SCENE.ground} strokeWidth="2.5" strokeLinecap="round" />
    </Frame>
  );
}

/** 4 · BILL — the invoice hand-off at the doorstep. */
export function SceneBill() {
  return (
    <Frame>
      {/* the door she stands in */}
      <rect x="176" y="46" width="52" height="95" fill={SCENE.cream2} />
      <rect x="183" y="56" width="38" height="85" rx="2" fill={SCENE.creamShade} />
      {/* the rider, invoice in hand */}
      <Villager x={66} y={140} variant="cap" dress={SCENE.sage} />
      <path d="M74 94Q86 96 96 100" stroke={SCENE.sage} strokeWidth="5" strokeLinecap="round" fill="none" />
      <circle cx="98" cy="101" r="3.2" fill={SCENE.skin} />
      {/* the invoice: a real document, passing between two hands */}
      <rect x="101" y="88" width="24" height="30" rx="2" transform="rotate(6 113 103)" fill={SCENE.paper} stroke={SCENE.creamShade} strokeWidth="1.2" />
      <path d="M107 96L121 97.5M106.5 101L120.5 102.5M106 106L116 107" stroke={SCENE.creamShade} strokeWidth="1.5" strokeLinecap="round" />
      <path d="M107 91.5L112 92" stroke={SCENE.dairy} strokeWidth="1.8" strokeLinecap="round" />
      {/* the customer, receiving it */}
      <Villager x={200} y={140} variant="bun" dress={SCENE.cream2} legs={SCENE.creamShade} flip />
      <path d="M192 96Q170 98 132 102" stroke={SCENE.cream2} strokeWidth="5" strokeLinecap="round" fill="none" />
      <circle cx="130" cy="102" r="3.2" fill={SCENE.skin} />
    </Frame>
  );
}

/** 5 · COLLECT — the settlement ledger, the payment, the receipt. */
export function SceneCollect() {
  return (
    <Frame>
      {/* the table */}
      <rect x="34" y="96" width="192" height="6" rx="3" fill={SCENE.creamShade} />
      <rect x="44" y="102" width="5" height="39" fill={SCENE.creamShade} />
      <rect x="211" y="102" width="5" height="39" fill={SCENE.creamShade} />
      {/* the open ledger */}
      <path d="M62 92Q88 84 112 92L112 60Q88 52 62 60Z" fill={SCENE.paper} stroke={SCENE.creamShade} strokeWidth="1.2" />
      <path d="M112 92Q136 84 162 92L162 60Q136 52 112 60Z" fill={SCENE.paper} stroke={SCENE.creamShade} strokeWidth="1.2" />
      <path d="M112 60V92" stroke={SCENE.creamShade} strokeWidth="1.4" />
      <path d="M70 66Q88 60 104 66M70 73Q88 67 104 73M70 80Q88 74 104 80M120 66Q138 60 154 66M120 73Q138 67 154 73" stroke={SCENE.creamShade} strokeWidth="1.4" fill="none" />
      {/* the entry that balances, in the dairy's own green */}
      <path d="M120 80Q138 74 148 78" stroke={SCENE.green} strokeWidth="2" fill="none" strokeLinecap="round" />
      {/* payment: notes and coins */}
      <rect x="176" y="74" width="34" height="17" rx="3" fill={SCENE.sage} stroke="#AFC3A2" strokeWidth="1.2" />
      <rect x="180" y="70" width="34" height="17" rx="3" fill={SCENE.green} stroke="#5CB877" strokeWidth="1.2" />
      <text x="197" y="82.5" textAnchor="middle" fontSize="10" fontWeight="700" fill={SCENE.dairy}>₹</text>
      <ellipse cx="222" cy="92" rx="7" ry="2.6" fill={SCENE.cream2} stroke={SCENE.creamShade} />
      <ellipse cx="222" cy="88.5" rx="7" ry="2.6" fill={SCENE.cream2} stroke={SCENE.creamShade} />
      <ellipse cx="222" cy="85" rx="7" ry="2.6" fill={SCENE.cream2} stroke={SCENE.creamShade} />
      {/* the receipt — torn edge, verified */}
      <g transform="rotate(-8 44 62)">
        <path d="M32 40H60V72L56 69L52 72L48 69L44 72L40 69L36 72L32 69Z" fill={SCENE.paper} stroke={SCENE.creamShade} strokeWidth="1.2" />
        <path d="M37 48H55M37 54H51" stroke={SCENE.creamShade} strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="46" cy="62" r="4.5" fill={SCENE.green} opacity="0.35" />
        <path d="M43.8 62L45.6 63.8L48.6 60.2" stroke={SCENE.dairy} strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </Frame>
  );
}

/** 6 · UNDERSTAND — the owner's view: the numbers agreeing, and the one
 * computed signal the platform raised (the only indigo in the set). */
export function SceneUnderstand() {
  return (
    <Frame>
      {/* the board */}
      <rect x="34" y="30" width="140" height="100" rx="8" fill={SCENE.paper} stroke={SCENE.creamShade} strokeWidth="1.2" />
      {/* bars: the days of collection */}
      {[
        [48, 74, 36],
        [66, 66, 44],
        [84, 80, 30],
        [102, 60, 50],
        [120, 70, 40],
      ].map(([x, y, h], i) => (
        <rect
          key={x}
          x={x}
          y={y}
          width="11"
          height={h}
          rx="2.5"
          fill={i === 3 ? SCENE.dairy : SCENE.sage}
        />
      ))}
      <path d="M44 118H166" stroke={SCENE.creamShade} strokeWidth="1.4" />
      {/* the sparkline, and the computed deviation the platform noticed */}
      <path d="M142 96L150 84L158 88L166 68" stroke={SCENE.green} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="166" cy="68" r="3.4" fill={SCENE.indigo} />
      <circle cx="166" cy="68" r="7" fill="none" stroke={SCENE.indigo} strokeWidth="1.4" opacity="0.45" />
      <path d="M150 52H166" stroke={SCENE.indigo} strokeWidth="2" strokeLinecap="round" opacity="0.6" />
      {/* the owner, taking it in */}
      <Villager x={216} y={140} variant="turban" dress={SCENE.cream2} />
      <path d="M209 92Q196 86 186 80" stroke={SCENE.cream2} strokeWidth="5" strokeLinecap="round" fill="none" />
      <circle cx="184" cy="79" r="3.2" fill={SCENE.skin} />
    </Frame>
  );
}
