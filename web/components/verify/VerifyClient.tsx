"use client";

import { useRouter } from "next/navigation";
import { SNAPSHOT_VERIFY, SOLSCAN_ACCOUNT, fetchVerify, fmtTime, usePolled, type VerifyReport, type VerifyRow } from "@/lib/api";
import { SOLSCAN_TX, short, slot } from "@/lib/featured";
import { CheckIcon, CopyButton, CopyHash, CrossIcon, ExternalIcon, LockIcon, Panel, Tag, TxLink, VerifiedCheck } from "@/components/live/ui";
import { ChainRun } from "./ChainRun";

const REPO = process.env.NEXT_PUBLIC_REPO_URL || "<repo>";

/* ---------- the five checks, derived from /v1/verify ---------- */

type Check = { title: string; explain: string; ok: boolean; count: string };

const has = (row: VerifyRow, ...needles: string[]) => (row.problems ?? []).some((p) => needles.some((n) => p.includes(n)));

function checks(v: VerifyReport): { list: Check[]; oaths: number } {
  const agents = Object.values(v.agents);
  const rows = agents.flatMap((a) => a.positions);
  const numbered = rows.length;
  const revealed = rows.filter((r) => r.reveal_sig);
  const traded = rows.filter((r) => r.swap_sig);
  const gaps = agents.flatMap((a) => a.gaps);
  const uncommitted = agents.reduce((n, a) => n + a.uncommitted_trades.length, 0);
  const disclosed = agents.reduce((n, a) => n + (a.disclosed_operator_actions?.length ?? 0), 0);
  const unrevealed = rows.filter((r) => r.status === "unrevealed").length;
  const hashBad = revealed.filter((r) => r.digest_ok === false || has(r, "sha256", "not in canonical", "thesis invalid")).length;
  const orderBad = traded.filter((r) => has(r, "did not land after")).length;
  const matchBad = traded.filter((r) => has(r, "does not match thesis", "entry spent", "exit swap invalid", "exit sold", "not sign", "swap tx not found")).length;
  return {
    oaths: numbered,
    list: [
      { title: "Sequence has no gaps", explain: numbered ? `Oaths 1…${numbered} are all on-chain, none skipped or hidden.` : "No oaths yet.",
        ok: gaps.length === 0, count: gaps.length ? `${gaps.length} missing` : `${numbered} contiguous` },
      { title: "Every revealed thesis hashes to its commit", explain: "sha256(thesis ‖ salt) equals the digest committed before the trade.",
        ok: hashBad === 0, count: `${revealed.length - hashBad}/${revealed.length} match` },
      { title: "Every commit landed before its trade", explain: "The commit memo's slot is lower than the swap's slot, so the plan came first.",
        ok: orderBad === 0, count: `${traded.length - orderBad}/${traded.length} in order` },
      { title: "Every trade was signed by the agent and matches its thesis",
        explain: `Mints and size match the revealed plan${disclosed ? `; ${disclosed} operator move disclosed on-chain, not a trade` : ""}.`,
        ok: matchBad === 0 && uncommitted === 0, count: `${traded.length - matchBad}/${traded.length} match · ${uncommitted} uncommitted` },
      { title: "No unrevealed oaths past their deadline", explain: "A missing reveal counts as a full loss, so hiding a bad call never pays.",
        ok: unrevealed === 0, count: `${unrevealed} overdue` },
    ],
  };
}

function Verdict({ v, live }: { v: VerifyReport; live: boolean }) {
  const { list, oaths } = checks(v);
  const failing = v.issues.length;
  return (
    <Panel className={`relative overflow-hidden p-5 sm:p-7 ${v.pass ? "border-[#A8D86E]/20" : "border-[#FF5A4E]/30"}`}>
      <div aria-hidden="true" className={`pointer-events-none absolute -left-20 -top-24 h-72 w-72 rounded-full blur-3xl ${v.pass ? "bg-[#3DFF6E]/[0.09]" : "bg-[#FF5A4E]/[0.09]"}`} />
      <div className="relative flex flex-wrap items-center gap-4">
        {v.pass ? <VerifiedCheck size={44} /> : (
          <span className="grid h-11 w-11 place-items-center rounded-full bg-[#FF5A4E]"><CrossIcon className="h-6 w-6" color="#fff" /></span>
        )}
        <div>
          <h2 className={`text-[26px] font-medium leading-tight tracking-[-0.02em] sm:text-[32px] ${v.pass ? "text-white" : "text-[#FF5A4E]"}`}>
            {v.pass ? "All checks pass" : `Problems found (${failing})`}
          </h2>
          <p className="mt-1 text-[13px] text-white/50">
            Last checked {fmtTime(Date.parse(v.checked_at) / 1000)} · {oaths} oaths · rebuilt from on-chain memos only
            {!live && <span className="text-[#FF5A4E]/80"> · API offline, showing the last snapshot</span>}
          </p>
        </div>
      </div>
      <ul className="relative mt-6 divide-y divide-white/[0.06] rounded-2xl border border-white/[0.07] bg-black/25">
        {list.map((c, i) => (
          <li key={c.title} className="flex items-start gap-3.5 px-4 py-3.5 sm:items-center sm:px-5">
            <span className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full sm:mt-0 ${c.ok ? "bg-[#A8D86E]" : "bg-[#FF5A4E]"}`}>
              {c.ok ? <CheckIcon className="h-3.5 w-3.5" color="#fff" /> : <CrossIcon className="h-3.5 w-3.5" color="#fff" />}
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-[14.5px] text-white"><span className="mr-1.5 font-mono text-[12px] text-white/30">{i + 1}</span>{c.title}</div>
              <div className="mt-0.5 text-[12.5px] leading-[18px] text-white/50">{c.explain}</div>
            </div>
            <span className={`shrink-0 text-right font-mono text-[12px] ${c.ok ? "text-white/60" : "text-[#FF5A4E]"}`}>{c.count}</span>
          </li>
        ))}
      </ul>
      {!!failing && (
        <ul className="relative mt-4 space-y-1 font-mono text-[12px] text-[#FF5A4E]">{v.issues.map((x) => <li key={x}>✗ {x}</li>)}</ul>
      )}
    </Panel>
  );
}

/* ---------- all oaths ---------- */

function statusTag(r: VerifyRow) {
  switch (r.status) {
    case "revealed": return <Tag tone="green">revealed</Tag>;
    case "blocked": return <Tag tone="red">blocked</Tag>;
    case "unrevealed": return <Tag tone="red">unrevealed</Tag>;
    case "open":
    case "committed": return <Tag tone="amber"><LockIcon className="h-3 w-3" /> open · sealed</Tag>;
    default: return <Tag tone="red">{r.status}</Tag>;
  }
}

function hashCell(r: VerifyRow) {
  if (r.status === "open" || r.status === "committed") return <span className="text-[12px] text-white/40">sealed</span>;
  if (r.digest_ok === true) return <span className="inline-flex items-center gap-1 text-[12.5px] text-[#A8D86E]"><CheckIcon className="h-3.5 w-3.5" /> match</span>;
  if (r.digest_ok === false) return <span className="inline-flex items-center gap-1 text-[12.5px] text-[#FF5A4E]"><CrossIcon className="h-3.5 w-3.5" /> mismatch</span>;
  return <span className="text-[12px] text-white/40">—</span>;
}

function OathTable({ v }: { v: VerifyReport }) {
  const router = useRouter();
  const rows = Object.values(v.agents).flatMap((a) => a.positions).sort((a, b) => b.seq - a.seq);
  const go = (seq: number) => router.push(`/oath/${seq}`);
  if (!rows.length) return <Panel className="p-6 text-center text-white/45">No oaths on-chain yet.</Panel>;
  return (
    <>
      {/* desktop table */}
      <Panel className="hidden overflow-hidden md:block">
        <table className="w-full text-left text-[13px]">
          <thead className="border-b border-white/[0.07] text-[11.5px] uppercase tracking-[0.06em] text-white/40">
            <tr>
              {["Seq", "Status", "Commit hash", "Commit slot", "Trade slot", "Hash check", "Solscan"].map((h) => (
                <th key={h} className="px-4 py-3 font-normal first:pl-5">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.05]">
            {rows.map((r) => (
              <tr key={r.seq} tabIndex={0} role="link" aria-label={`Open Oath #${r.seq}`} onClick={() => go(r.seq)}
                  onKeyDown={(e) => e.key === "Enter" && go(r.seq)}
                  className="cursor-pointer transition-colors hover:bg-white/[0.03] focus-visible:bg-white/[0.04] focus-visible:outline-none">
                <td className="px-4 py-3.5 pl-5 font-mono text-white">#{r.seq}</td>
                <td className="px-4 py-3.5">{statusTag(r)}</td>
                <td className="px-4 py-3.5 font-mono text-white/70" title={r.digest}>{short(r.digest, 8, 6)}</td>
                <td className="px-4 py-3.5 font-mono text-white/60">{slot(r.commit_slot)}</td>
                <td className="px-4 py-3.5 font-mono text-white/60">{slot(r.swap_slot)}</td>
                <td className="px-4 py-3.5">{hashCell(r)}</td>
                <td className="px-4 py-3.5">
                  <div className="flex gap-3">
                    <TxLink sig={r.commit_sig ?? r.blocked_sig} label="commit" />
                    <TxLink sig={r.swap_sig} label="swap" />
                    <TxLink sig={r.reveal_sig} label="reveal" />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      {/* mobile cards */}
      <div className="grid gap-2.5 md:hidden">
        {rows.map((r) => (
          <div key={r.seq} role="link" tabIndex={0} aria-label={`Open Oath #${r.seq}`} onClick={() => go(r.seq)}
               onKeyDown={(e) => e.key === "Enter" && go(r.seq)} className="cursor-pointer">
            <Panel className="p-4">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[15px] text-white">Oath #{r.seq}</span>
                {statusTag(r)}
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-[12px]">
                <dt className="text-white/40">Commit hash</dt><dd className="text-right font-mono text-white/70">{short(r.digest, 6, 6)}</dd>
                <dt className="text-white/40">Commit slot</dt><dd className="text-right font-mono text-white/60">{slot(r.commit_slot)}</dd>
                <dt className="text-white/40">Trade slot</dt><dd className="text-right font-mono text-white/60">{slot(r.swap_slot)}</dd>
                <dt className="text-white/40">Hash check</dt><dd className="text-right">{hashCell(r)}</dd>
              </dl>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-white/[0.06] pt-3">
                <TxLink sig={r.commit_sig ?? r.blocked_sig} label="commit tx" />
                <TxLink sig={r.swap_sig} label="swap tx" />
                <TxLink sig={r.reveal_sig} label="reveal tx" />
              </div>
            </Panel>
          </div>
        ))}
      </div>
    </>
  );
}

/* ---------- run it yourself ---------- */

function CopyBlock({ lines }: { lines: string[] }) {
  const text = lines.join("\n");
  return (
    <div className="relative rounded-xl border border-white/[0.08] bg-black/50">
      <pre className="overflow-x-auto p-4 pr-16 font-mono text-[12.5px] leading-[20px] text-white/85">
        {lines.map((l) => <div key={l}><span className="select-none text-[#A8D86E]">$ </span>{l}</div>)}
      </pre>
      <div className="absolute right-2.5 top-2.5"><CopyButton value={text} /></div>
    </div>
  );
}

const EXPLAIN = [
  { t: "Commit", d: "Before any trade, OATH posts a fingerprint (sha256 hash) of its full plan on Solana. The plan stays secret, but it can't be changed later." },
  { t: "Salt", d: "32 random bytes mixed into the hash, so nobody can guess the plan by trying likely prices. It's published at the reveal." },
  { t: "Reveal", d: "After the trade closes, OATH publishes the plan and salt. Anyone can hash them again: same fingerprint means same plan." },
];

function RunYourself({ notary }: { notary: string }) {
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
      <Panel className="min-w-0 p-5">
        <h3 className="text-[15px] font-medium text-white">For technical users</h3>
        <p className="mt-1 text-[13px] text-white/50">The same checks, in Python, from any machine. No account, no API key, only a public RPC.</p>
        <div className="mt-4">
          <CopyBlock lines={[`git clone ${REPO} && cd OATH`, `uv run python -m oath_core.verify --notary ${notary}`]} />
        </div>
        <div className="mt-4 text-[12.5px] text-white/45">Notary wallet (signs every oath memo)</div>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <CopyHash value={notary} head={10} tail={10} />
          <a href={SOLSCAN_ACCOUNT(notary)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[12.5px] text-white/50 hover:text-[#A8D86E]">
            Solscan <ExternalIcon />
          </a>
        </div>
      </Panel>
      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
        {EXPLAIN.map((e, i) => (
          <Panel key={e.t} className="p-4">
            <div className="flex items-center gap-2">
              <span className="grid h-6 w-6 place-items-center rounded-full border border-white/10 font-mono text-[11px] text-white/60">{i + 1}</span>
              <span className="text-[14.5px] text-white">{e.t}</span>
            </div>
            <p className="mt-2 text-[12.5px] leading-[18px] text-white/55">{e.d}</p>
          </Panel>
        ))}
      </div>
    </div>
  );
}

/* ---------- page ---------- */

export function VerifyClient() {
  const { data: v, live } = usePolled(fetchVerify, SNAPSHOT_VERIFY, 30_000);
  return (
    <div className="mx-auto w-full max-w-[1100px] px-4 pb-24 pt-8 sm:px-8 sm:pt-12">
      <header>
        <p className="font-mono text-[12px] uppercase tracking-[0.12em] text-[#A8D86E]">Don&apos;t trust us. Check it.</p>
        <h1 className="headline-gradient mt-2 text-[44px] font-medium leading-[1] tracking-[-0.035em] sm:text-[64px]">Verify</h1>
        <p className="mt-3 max-w-[640px] text-[16px] text-white/60 sm:text-[18px]">
          Every oath OATH has ever taken, checked against Solana. No account, no trust.
        </p>
      </header>

      <div className="mt-8"><Verdict v={v} live={live} /></div>

      <section className="mt-12" aria-labelledby="chain-h">
        <h2 id="chain-h" className="text-[22px] font-medium tracking-[-0.02em] text-white">Verify from the chain, in your browser</h2>
        <p className="mt-1.5 max-w-[680px] text-[14px] text-white/55">
          Skip our API entirely. Your browser reads the notary&apos;s transactions straight from a public Solana RPC, re-hashes every revealed thesis and checks the order of every step.
        </p>
        <div className="mt-5"><ChainRun notary={v.notary} expected={checks(v).oaths} /></div>
      </section>

      <section className="mt-12" aria-labelledby="all-h">
        <div className="flex items-baseline justify-between gap-3">
          <h2 id="all-h" className="text-[22px] font-medium tracking-[-0.02em] text-white">All oaths</h2>
          <a href={SOLSCAN_TX(v.notary).replace("/tx/", "/account/")} target="_blank" rel="noreferrer" className="text-[12.5px] text-white/45 hover:text-[#A8D86E]">
            notary {short(v.notary, 4, 4)} ↗
          </a>
        </div>
        <div className="mt-4"><OathTable v={v} /></div>
      </section>

      <section className="mt-12" aria-labelledby="run-h">
        <h2 id="run-h" className="text-[22px] font-medium tracking-[-0.02em] text-white">Run it yourself</h2>
        <div className="mt-4"><RunYourself notary={v.notary} /></div>
      </section>
    </div>
  );
}
