"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { OathWordmark } from "./Logo";

type NavLink = { href: string; label: string };

const noop = () => () => {};

/** Below 768px: a hamburger that opens a full-screen menu (portalled to <body>, so no card clips it). */
export function MobileMenu({ links, active, cta }: { links: NavLink[]; active?: string; cta: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const reduce = useReducedMotion();
  const mounted = useSyncExternalStore(noop, () => true, () => false);
  const burger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  const leaving = useRef(false); // closing because a link was followed: don't restore the old scroll
  const close = useCallback(() => setOpen(false), []);
  const follow = useCallback(() => {
    leaving.current = true;
    setOpen(false);
  }, []);

  // lock page scroll, Escape to close, keep Tab inside the menu, close if the viewport grows past md
  useEffect(() => {
    if (!open) return;
    // Pin the body where it is (overflow:hidden on <html> would jump the page to the top here,
    // because html already has overflow-x: clip), then put the scroll position back on close.
    const body = document.body;
    const y = window.scrollY;
    const prev = body.getAttribute("style");
    Object.assign(body.style, { position: "fixed", top: `-${y}px`, left: "0", right: "0", width: "100%", overflow: "hidden" });
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
        return;
      }
      if (e.key !== "Tab" || !panel.current) return;
      const f = panel.current.querySelectorAll<HTMLElement>("a[href], button:not([disabled])");
      if (!f.length) return;
      const first = f[0];
      const last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    const mq = window.matchMedia("(min-width: 768px)");
    const onMq = () => mq.matches && close();
    document.addEventListener("keydown", onKey);
    mq.addEventListener("change", onMq);
    const t = setTimeout(() => panel.current?.querySelector<HTMLElement>("[data-autofocus]")?.focus(), 30);
    const btn = burger.current;
    return () => {
      if (prev === null) body.removeAttribute("style");
      else body.setAttribute("style", prev);
      if (!leaving.current) window.scrollTo({ top: y, behavior: "instant" });
      leaving.current = false;
      document.removeEventListener("keydown", onKey);
      mq.removeEventListener("change", onMq);
      clearTimeout(t);
      btn?.focus({ preventScroll: true });
    };
  }, [open, close]);

  const dur = reduce ? 0 : 0.32;
  const ease = [0.22, 1, 0.36, 1] as const;

  return (
    <>
      <button
        ref={burger}
        type="button"
        aria-label="Open menu"
        aria-expanded={open}
        aria-controls="mobile-menu"
        onClick={() => setOpen(true)}
        className="grid h-[36px] w-[36px] place-items-center rounded-full border border-white/[0.07] bg-[#1b1b1c] text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] transition-colors hover:bg-[#232324] md:hidden"
      >
        <svg viewBox="0 0 20 20" className="h-[18px] w-[18px]" fill="none" aria-hidden="true">
          <path d="M3.5 6.5h13M3.5 13.5h13" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
      </button>

      {mounted &&
        createPortal(
          <AnimatePresence>
            {open && (
              <motion.div
                key="menu"
                id="mobile-menu"
                ref={panel}
                role="dialog"
                aria-modal="true"
                aria-label="Menu"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: dur, ease }}
                className="subpage grain fixed inset-0 z-[80] flex flex-col overflow-y-auto md:hidden"
              >
                <div aria-hidden="true" className="pointer-events-none fixed inset-x-0 bottom-0 h-[40vh] bg-[radial-gradient(60%_80%_at_50%_100%,rgba(61,255,110,0.12),transparent)]" />
                <div className="relative flex h-[60px] shrink-0 items-center justify-between px-5">
                  <Link href="/" aria-label="OATH home" onClick={follow}>
                    <OathWordmark className="h-[24px] w-auto" />
                  </Link>
                  <button
                    type="button"
                    data-autofocus
                    aria-label="Close menu"
                    onClick={close}
                    className="grid h-[36px] w-[36px] place-items-center rounded-full border border-white/[0.07] bg-[#1b1b1c] text-white transition-colors hover:bg-[#232324]"
                  >
                    <svg viewBox="0 0 20 20" className="h-[16px] w-[16px]" fill="none" aria-hidden="true">
                      <path d="M5 5l10 10M15 5 5 15" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
                    </svg>
                  </button>
                </div>

                <nav aria-label="Main" className="relative flex flex-1 flex-col px-5 pt-6">
                  {links.map((l, i) => (
                    <motion.div
                      key={l.href}
                      initial={{ opacity: 0, y: reduce ? 0 : 14 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: dur, ease, delay: reduce ? 0 : 0.04 + i * 0.04 }}
                    >
                      <Link
                        href={l.href}
                        onClick={follow}
                        aria-current={active === l.href ? "page" : undefined}
                        className={`flex items-center justify-between border-b border-white/[0.07] py-4 text-[30px] font-medium tracking-[-0.02em] transition-colors ${
                          active === l.href ? "text-white" : "text-white/60 hover:text-white"
                        }`}
                      >
                        {l.label}
                        {active === l.href && (
                          <span aria-hidden="true" className="h-[6px] w-[6px] rounded-full bg-[#A8D86E] shadow-[0_0_10px_#3DFF6E]" />
                        )}
                      </Link>
                    </motion.div>
                  ))}
                </nav>

                <motion.div
                  initial={{ opacity: 0, y: reduce ? 0 : 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: dur, ease, delay: reduce ? 0 : 0.26 }}
                  className="relative px-5 pb-[max(24px,env(safe-area-inset-bottom))] pt-8"
                  onClick={(e) => (e.target as HTMLElement).closest("a") && follow()}
                >
                  {cta}
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>,
          document.body,
        )}
    </>
  );
}
