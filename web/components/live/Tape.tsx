"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { EXIT_LABEL, fmtAgo, fmtPnl, fmtTime, humanCode, trimAmount, type FeedItem, type Position } from "@/lib/api";
import { short, slot } from "@/lib/featured";
import { useNow } from "@/lib/useNow";
import { type Filter, type TapeRow, buildTape, matchFilter } from "./rows";
import { BlockIcon, CheckIcon, CrossIcon, FlagIcon, LockIcon, Panel, PauseIcon, SwapIcon, Tag, TxLink } from "./ui";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "trades", label: "Trades" },
  { id: "blocked", label: "Blocked" },
  { id: "stood_aside", label: "Stood aside" },
];

/* per-seq rail colour, so a seq's rows read as one thread */
const RAIL = ["#A8D86E", "#7fb2ff", "#F2C14E", "#c79bff", "#5fd6c4"];
const railColor = (seq: number) => RAIL[(seq - 1) % RAIL.length];

function Icon({ row }: { row: TapeRow }) {
  const wrap = "grid h-8 w-8 shrink-0 place-items-center rounded-full border";
  switch (row.kind) {
    case "commit":
      return <span className={`${wrap} border-[#F2C14E]/30 bg-[#F2C14E]/[0.08]`}><LockIcon /></span>;
    case "open":
      return <span className={`${wrap} border-white/10 bg-white/[0.04]`}><SwapIcon /></span>;
    case "close":
      return <span className={`${wrap} border-white/10 bg-white/[0.04]`}><FlagIcon className="h-4 w-4" /></span>;
    case "reveal":
      return row.pos?.digest_ok === false
        ? <span className={`${wrap} border-[#FF5A4E]/40 bg-[#FF5A4E]/10`}><CrossIcon /></span>
        : <span className={`${wrap} border-transparent bg-[#A8D86E] shadow-[0_0_14px_rgba(61,255,110,0.45)]`}><CheckIcon color="#fff" /></span>;
    case "blocked":
    case "slash":
      return <span className={`${wrap} border-[#FF5A4E]/30 bg-[#FF5A4E]/[0.08]`}><BlockIcon /></span>;
    default:
      return <span className={`${wrap} border-white/[0.07] bg-transparent`}><PauseIcon /></span>;
  }
}

function signalsLine(it: FeedItem | null) {
  const ev = it?.evidence;
  if (!ev || typeof ev.agreeing !== "number") return null;
  const total = ev.signals?.length;
  return `${ev.agreeing}${total ? `/${total}` : ""} agreeing, needs ${ev.needs ?? "?"}`;
}

function Body({ row }: { row: TapeRow }) {
  const it = row.item;
  const p = row.pos;
  const oath = row.seq !== null ? `Oath #${row.seq}` : "";
  switch (row.kind) {
    case "commit":
      return (
        <>
          <div className="text-[14.5px] text-white"><span className="text-[#F2C14E]">Committed</span> · {oath}</div>
          <div className="mt-0.5 font-mono text-[12px] text-white/50">
            hash <span className="text-white/75" title={it?.digest}>{short(it?.digest, 8, 6)}</span> · slot {slot(it?.slot)}
          </div>
        </>
      );
    case "open":
      return (
        <>
          <div className="text-[14.5px] text-white">Trade opened · {oath}</div>
          <div className="mt-0.5 font-mono text-[12px] text-white/60" title={p?.entry?.summary}>
            {p?.entry ? <>{trimAmount(p.entry.spent, 2)} <span className="text-white/35">→</span> {trimAmount(p.entry.received)}</> : "fill pending index"}
          </div>
        </>
      );
    case "close": {
      const pnl = p?.result?.pnl_usd;
      const n = Number(pnl);
      return (
        <>
          <div className="text-[14.5px] text-white">
            Closed · {oath} <span className="text-white/45">· {EXIT_LABEL[p?.exit_reason ?? ""] ?? p?.exit_reason ?? "exit"}</span>
          </div>
          <div className="mt-0.5 font-mono text-[12px] text-white/60" title={p?.exit?.summary}>
            {p?.exit && <>{trimAmount(p.exit.spent)} <span className="text-white/35">→</span> {trimAmount(p.exit.received, 2)} · </>}
            <span className="whitespace-nowrap">P&amp;L</span> <span className={`whitespace-nowrap ${n < 0 ? "text-[#FF5A4E]" : n > 0 ? "text-[#A8D86E]" : "text-white/70"}`}>{fmtPnl(pnl)}</span>
          </div>
        </>
      );
    }
    case "reveal":
      return (
        <>
          <div className="flex flex-wrap items-center gap-2 text-[14.5px] text-white">
            Revealed · {oath}
            {p?.digest_ok === false ? <Tag tone="red">hash mismatch</Tag> : <Tag tone="green"><CheckIcon className="h-3 w-3" /> hash verified</Tag>}
          </div>
          <div className="mt-0.5 truncate text-[12.5px] text-white/50">
            {p?.thesis?.why ? <>&ldquo;{p.thesis.why}&rdquo;</> : "thesis and salt published on-chain"}
          </div>
        </>
      );
    case "blocked":
      return (
        <>
          <div className="text-[14.5px] text-white"><span className="text-[#FF5A4E]">Blocked</span> · {oath}</div>
          <div className="mt-0.5 font-mono text-[12px] text-[#FF5A4E]/80">{it?.reason_code ?? "firewall"}</div>
        </>
      );
    case "slash":
      return <div className="text-[14.5px] text-[#FF5A4E]">Slashed · {oath}</div>;
    case "stand_aside":
      return (
        <>
          <div className="flex flex-wrap items-center gap-2 text-[14.5px] text-white/70">
            Stood aside <span className="text-white/40">· {humanCode(it?.reason_code)}</span>
            {it?.evidence?.backfilled && <Tag>backfilled</Tag>}
          </div>
          <div className="mt-0.5 font-mono text-[12px] text-white/45">{signalsLine(it) ?? it?.why}</div>
        </>
      );
    case "operator_disclosure":
      return (
        <>
          <div className="flex flex-wrap items-center gap-2 text-[14.5px] text-white/70">
            Operator disclosure <span className="text-white/40">· {humanCode(it?.reason)}</span>
            <Tag>not a trade</Tag>
          </div>
          <div className="mt-0.5 text-[12.5px] text-white/45">Housekeeping move from the agent wallet, declared on-chain.</div>
        </>
      );
    default:
      return <div className="text-[14.5px] text-white/70">{row.kind}</div>;
  }
}

function rowTx(row: TapeRow): { sig?: string; label: string } {
  const it = row.item;
  switch (row.kind) {
    case "commit": return { sig: it?.sig, label: "commit tx" };
    case "open": return { sig: it?.swap_sig ?? it?.sig, label: "swap tx" };
    case "close": return { sig: row.pos?.exit_sig, label: "exit tx" };
    case "reveal": return { sig: it?.sig, label: "reveal tx" };
    case "operator_disclosure": return { sig: it?.tx_sig ?? it?.sig, label: "tx" };
    default: return { sig: it?.sig, label: "tx" };
  }
}

export function Tape({ feed, positions }: { feed: FeedItem[]; positions: Position[] }) {
  const router = useRouter();
  const now = useNow();
  const reduce = useReducedMotion();
  const [filter, setFilter] = useState<Filter>("all");
  const [hoverSeq, setHoverSeq] = useState<number | null>(null);
  const [openKey, setOpenKey] = useState<string | null>(null);

  const all = useMemo(() => buildTape(feed, positions), [feed, positions]);
  const rows = all.filter((r) => matchFilter(r, filter));
  const counts = useMemo(() => Object.fromEntries(FILTERS.map((f) => [f.id, all.filter((r) => matchFilter(r, f.id)).length])), [all]);

  // rows present at first paint don't flash; anything that arrives later does
  const [initialKeys] = useState(() => new Set(all.map((r) => r.key)));
  const isNew = (k: string) => !initialKeys.has(k);

  return (
    <Panel className="overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.06] px-4 py-3.5 sm:px-5">
        <div className="flex items-baseline gap-2.5">
          <h2 className="text-[17px] font-medium tracking-[-0.01em] text-white">The tape</h2>
          <span className="text-[12.5px] text-white/40">newest first</span>
        </div>
        <div role="tablist" aria-label="Filter the tape" className="flex max-w-full gap-1 overflow-x-auto rounded-full border border-white/[0.07] bg-black/30 p-1">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              role="tab"
              aria-selected={filter === f.id}
              onClick={() => setFilter(f.id)}
              className={`shrink-0 rounded-full px-3 py-1 text-[12.5px] transition-colors ${
                filter === f.id ? "bg-white text-black" : "text-white/60 hover:text-white"
              }`}
            >
              {f.label} <span className={filter === f.id ? "text-black/45" : "text-white/30"}>{counts[f.id]}</span>
            </button>
          ))}
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="px-5 py-10 text-center text-[14px] text-white/45">Nothing here yet. Every event lands on this tape the moment it&apos;s on-chain.</p>
      ) : (
        <ol className="relative">
          <AnimatePresence initial={false}>
            {rows.map((row, i) => {
              const prev = rows[i - 1];
              const next = rows[i + 1];
              const linkUp = row.seq !== null && prev?.seq === row.seq;
              const linkDown = row.seq !== null && next?.seq === row.seq;
              const clickable = row.seq !== null;
              const expandable = row.kind === "stand_aside" && !!row.item?.evidence?.signals?.length;
              const dim = hoverSeq !== null && row.seq !== hoverSeq;
              const tx = rowTx(row);
              const fresh = isNew(row.key);
              return (
                <motion.li
                  key={row.key}
                  layout={reduce ? false : "position"}
                  initial={fresh && !reduce ? { opacity: 0, y: -14, backgroundColor: "rgba(61,255,110,0.16)" } : false}
                  animate={{ opacity: dim ? 0.45 : 1, y: 0, backgroundColor: "rgba(61,255,110,0)" }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: fresh ? 0.9 : 0.25, ease: [0.22, 1, 0.36, 1] }}
                  onMouseEnter={() => setHoverSeq(row.seq)}
                  onMouseLeave={() => setHoverSeq(null)}
                  onClick={() => {
                    if (clickable) router.push(`/oath/${row.seq}`);
                    else if (expandable) setOpenKey(openKey === row.key ? null : row.key);
                  }}
                  onKeyDown={(e) => {
                    if (e.key !== "Enter" && e.key !== " ") return;
                    e.preventDefault();
                    if (clickable) router.push(`/oath/${row.seq}`);
                    else if (expandable) setOpenKey(openKey === row.key ? null : row.key);
                  }}
                  tabIndex={clickable || expandable ? 0 : undefined}
                  role={clickable ? "link" : expandable ? "button" : undefined}
                  aria-label={clickable ? `Open Oath #${row.seq}` : undefined}
                  className={`group relative flex gap-3 border-b border-white/[0.045] py-3.5 pl-4 pr-4 last:border-b-0 sm:gap-4 sm:pl-5 sm:pr-5 ${
                    clickable || expandable ? "cursor-pointer hover:bg-white/[0.025] focus-visible:bg-white/[0.035] focus-visible:outline-none" : ""
                  }`}
                >
                  {/* seq thread: a coloured rail that joins rows of the same oath */}
                  {row.seq !== null && (
                    <span
                      aria-hidden="true"
                      className="absolute left-0 w-[3px] rounded-full"
                      style={{ background: railColor(row.seq), top: linkUp ? 0 : 14, bottom: linkDown ? 0 : 14, opacity: 0.75 }}
                    />
                  )}
                  <div className="relative flex flex-col items-center">
                    {linkUp && <span aria-hidden="true" className="absolute -top-3.5 h-3.5 w-px bg-white/12" />}
                    <Icon row={row} />
                    {linkDown && <span aria-hidden="true" className="absolute top-8 -bottom-3.5 w-px bg-white/12" />}
                  </div>
                  <div className="min-w-0 flex-1">
                    <Body row={row} />
                    {expandable && openKey === row.key && (
                      <ul className="mt-2.5 space-y-1.5 rounded-lg border border-white/[0.06] bg-black/25 p-2.5">
                        {row.item!.evidence!.signals!.map((s) => (
                          <li key={s.name} className="flex items-center gap-2 text-[12.5px]">
                            {s.agrees ? <CheckIcon className="h-3.5 w-3.5" /> : <CrossIcon className="h-3.5 w-3.5" color="#6f6f6f" />}
                            <span className="text-white/70">{s.name}</span>
                            <span className="ml-auto font-mono text-white/45">{s.reading}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 sm:hidden">
                      <span className="font-mono text-[11.5px] text-white/40">{fmtTime(row.time)}</span>
                      <TxLink sig={tx.sig} label={tx.label} />
                    </div>
                  </div>
                  <div className="hidden shrink-0 flex-col items-end gap-1 text-right sm:flex">
                    <span className="font-mono text-[11.5px] text-white/55" title={fmtTime(row.time)}>{now ? fmtAgo(row.time, now) : fmtTime(row.time, false)}</span>
                    <span className="font-mono text-[11px] text-white/30">{fmtTime(row.time)}</span>
                    <TxLink sig={tx.sig} label={tx.label} />
                  </div>
                  {clickable && (
                    <span aria-hidden="true" className="hidden self-center text-white/20 transition-colors group-hover:text-white/60 sm:block">›</span>
                  )}
                </motion.li>
              );
            })}
          </AnimatePresence>
        </ol>
      )}
      <p className="border-t border-white/[0.06] px-4 py-3 text-[11.5px] leading-[17px] text-white/35 sm:px-5">
        Commits, trades, closes and reveals are read from Solana. Stand-asides are off-chain decisions recorded by the agent (nothing to commit when it doesn&apos;t trade).
      </p>
    </Panel>
  );
}
