/* OATH demo: every visual is a pure function of time t (seconds), so frame N always renders the same.
   window.renderFrame(n) is driven by record.mjs at 30 fps. Data: window.OATH (data.js, real). */
(() => {
  const D = window.OATH;
  const FPS = 30;
  const TOTAL = 60;
  const $ = (id) => document.getElementById(id);
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const seg = (t, a, b) => clamp((t - a) / (b - a));
  const out3 = (x) => 1 - Math.pow(1 - clamp(x), 3);
  const inOut = (x) => { x = clamp(x); return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };
  const back = (x) => { x = clamp(x); const c = 1.7; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); };
  const typed = (s, p) => s.slice(0, Math.round(s.length * clamp(p)));
  const fmtSlot = (n) => n.toLocaleString("en-US");
  const show = (el, p, dy = 30) => { el.style.opacity = p; el.style.transform = `translateY(${(1 - p) * dy}px)`; };
  const trim = (a, dp) => { const [n, u] = a.split(" "); return `${Number(n).toFixed(dp)} ${u}`; };
  const group = (h) => (h.match(/.{1,8}/g) || []).join(" ");
  // hash split into fixed lines of `per` 8-char groups, so it never wraps mid-group
  const lines = (h, per) => { const g = h.match(/.{1,8}/g) || []; const out = []; for (let i = 0; i < g.length; i += per) out.push(g.slice(i, i + per).join(" ")); return out.join("<br>"); };
  const cursor = '<span class="cursor"></span>';

  // [id, start, end]
  const SCENES = [["s1", 0, 5], ["s2", 5, 12], ["s3", 12, 20], ["s4", 20, 28], ["s5", 28, 36], ["s6", 36, 42], ["s7", 42, 50], ["s8", 50, 56], ["s9", 56, 60]];
  const FADE = 0.45;

  /* ---------- static fill (real data) ---------- */
  const T = D.thesis;
  $("s3-time").textContent = D.signals_time;
  $("s3-rows").innerHTML = D.signals.map((s, i) => `
    <div class="sig-row ${s.state}" id="s3-r${i}">
      <div class="ic">${s.state === "agree" ? "✓" : "–"}</div>
      <div class="nm">${s.name}</div>
      <div class="rd">${s.reading}</div>
    </div>`).join("");

  const money = (v) => `$${Number(v).toFixed(2)}`;
  const TH = [
    ["Market", `${T.mkt} · ${T.side}`, ""],
    ["Entry", money(T.entry), `${T.entry} USDC per SOL`],
    ["Stop", money(T.stop), "−3%"],
    ["Take-profit", money(T.tp), "+5%"],
    ["Size", `${T.size_usd} USDC`, "small test size"],
    ["Horizon", `${T.horizon_min} min`, ""],
    ["Why", T.why, ""],
  ];
  $("s4-rows").innerHTML = TH.map((r, i) => `
    <div class="th-row ${r[0] === "Why" ? "why" : ""}" id="s4-r${i}"><div class="k">${r[0]}</div><div class="v" id="s4-v${i}"></div></div>`).join("");

  // canonical JSON shown one key per line (same bytes, just wrapped for reading)
  const prettyCanon = Object.keys(T).sort().filter((k) => !["agent", "in_mint", "out_mint"].includes(k))
    .map((k) => `"${k}":"${T[k]}"`).join(",\n") + ",\n…";
  $("s5-salt-v").textContent = `${D.salt.slice(0, 12)}…${D.salt.slice(-6)}`;
  $("s5-slot").textContent = fmtSlot(D.commit.slot);
  $("s5-time").textContent = D.commit.time;

  $("s6-in-v").textContent = trim(D.swap.spent, 2);
  $("s6-out-v").textContent = trim(D.swap.received, 6);
  $("s6-slot").textContent = fmtSlot(D.swap.slot);
  $("s6-m1v").textContent = fmtSlot(D.commit.slot);
  $("s6-m2v").textContent = fmtSlot(D.swap.slot);

  $("s7-slot").textContent = fmtSlot(D.reveal.slot);
  $("s7-exit-v").textContent = `${trim(D.exit.spent, 6)} → ${trim(D.exit.received, 4)}`;
  $("s7-pnl").textContent = `real P&L on a 1-USDC test: −$${Math.abs(Number(D.pnl_usd)).toFixed(4)}`;
  $("s7-committed").innerHTML = lines(D.digest, 4);

  $("s8-stop").textContent = T.stop;
  $("s8-tp").textContent = T.tp;
  $("s8-committed").innerHTML = lines(D.digest, 4);

  /* ---------- scenes ---------- */
  const S = {
    s1(t) {
      const p = out3(seg(t, 0.1, 1.2));
      $("s1-seal").style.transform = `scale(${0.6 + 0.4 * back(seg(t, 0.1, 1.2))})`;
      $("s1-seal").style.opacity = p;
      const ring = seg(t, 0.6, 2.4);
      $("s1-ring").style.transform = `scale(${1 + ring * 0.9})`;
      $("s1-ring").style.opacity = (1 - ring) * 0.9;
      show($("s1-word"), out3(seg(t, 0.8, 1.6)), 20);
      show($("s1-cap"), out3(seg(t, 1.6, 2.5)), 40);
    },
    s2(t) {
      show($("s2-cap"), out3(seg(t, 0, 0.7)));
      show($("s2-bot"), out3(seg(t, 0.4, 1.2)), 40);
      const rows = [...$("s2-rows").children];
      const strike = seg(t, 2.6, 3.2);
      const gone = inOut(seg(t, 3.3, 4.3));
      rows.forEach((r, i) => {
        const base = out3(seg(t, 0.9 + i * 0.18, 1.4 + i * 0.18));
        let h = 64, op = base, deco = "none";
        if (r.classList.contains("loss")) {
          deco = strike > 0 ? "line-through" : "none";
          op = base * (1 - gone);
          h = 64 * (1 - gone);
        }
        r.style.opacity = op; r.style.height = `${h}px`; r.style.lineHeight = "64px";
        r.style.textDecoration = deco; r.style.textDecorationColor = "#FF5A4E";
      });
      const rate = $("s2-rate");
      const after = t > 4.3;
      rate.textContent = after ? "100%" : "60%";
      rate.style.color = after ? "#A8D86E" : "#fff";
      rate.style.textShadow = after ? "0 0 24px rgba(61,255,110,0.7)" : "none";
      show($("s2-side"), out3(seg(t, 4.5, 5.3)), 30);
    },
    s3(t) {
      show($("s3-cap"), out3(seg(t, 0, 0.7)));
      show($("s3-card"), out3(seg(t, 0.3, 1.0)), 40);
      D.signals.forEach((_, i) => {
        const el = $(`s3-r${i}`);
        const p = out3(seg(t, 1.0 + i * 0.75, 1.5 + i * 0.75));
        el.style.opacity = p; el.style.transform = `translateX(${(1 - p) * -30}px)`;
        const ic = el.querySelector(".ic");
        ic.style.transform = `scale(${back(seg(t, 1.3 + i * 0.75, 1.8 + i * 0.75))})`;
      });
      show($("s3-result"), out3(seg(t, 4.3, 5.0)), 20);
      show($("s3-note"), out3(seg(t, 5.0, 5.6)), 10);
    },
    s4(t) {
      show($("s4-cap"), out3(seg(t, 0, 0.7)));
      show($("s4-card"), out3(seg(t, 0.3, 1.0)), 40);
      const start = 1.0, per = 0.78;
      TH.forEach((r, i) => {
        const row = $(`s4-r${i}`);
        const a = start + i * per, b = a + per * 0.8;
        row.style.opacity = t >= a - 0.05 ? 1 : 0;
        const p = seg(t, a, b);
        const typing = t >= a && t < b;
        const isLast = i === TH.length - 1;
        const blink = Math.floor(t * 2) % 2 === 0;
        const cur = typing || (isLast && t >= b && blink) ? cursor : "";
        $(`s4-v${i}`).innerHTML = typed(r[1], p) + (p >= 1 && r[2] ? `<small>${r[2]}</small>` : "") + cur;
      });
    },
    s5(t) {
      show($("s5-cap"), out3(seg(t, 0, 0.7)));
      show($("s5-thesis"), out3(seg(t, 0.3, 1.0)), 40);
      $("s5-json").textContent = prettyCanon;
      show($("s5-salt"), out3(seg(t, 1.1, 1.7)), 20);
      $("s5-mid").style.opacity = 1;
      document.querySelector(".plus").style.opacity = out3(seg(t, 0.9, 1.3));
      const sha = $("s5-sha");
      sha.style.opacity = out3(seg(t, 1.8, 2.3));
      sha.style.transform = `scale(${0.9 + 0.1 * back(seg(t, 1.8, 2.3))})`;
      show($("s5-hashcard"), out3(seg(t, 2.0, 2.6)), 40);
      $("s5-hash").innerHTML = lines(typed(D.digest, seg(t, 2.4, 3.8)), 2);
      // lock: the thesis card turns amber
      const lock = out3(seg(t, 3.9, 4.4));
      const card = $("s5-thesis");
      card.style.borderColor = `rgba(242,193,78,${0.09 + lock * 0.6})`;
      card.style.boxShadow = `0 0 ${lock * 70}px rgba(242,193,78,${lock * 0.25}), 0 30px 80px rgba(0,0,0,0.5)`;
      $("s5-json").style.filter = `blur(${lock * 5}px)`;
      $("s5-json").style.opacity = 1 - lock * 0.55;
      const lk = $("s5-lock");
      lk.style.opacity = lock; lk.style.transform = `scale(${0.8 + 0.2 * back(seg(t, 3.9, 4.4))})`;
      const st = $("s5-stamp");
      const sp = seg(t, 4.3, 4.9);
      st.style.opacity = out3(sp);
      st.style.transform = `translateX(-50%) scale(${1.25 - 0.25 * out3(sp)})`;
    },
    s6(t) {
      show($("s6-cap"), out3(seg(t, 0, 0.7)));
      show($("s6-in"), out3(seg(t, 0.4, 1.0)), 30);
      document.querySelector(".swap-arrow").style.opacity = out3(seg(t, 0.8, 1.1));
      $("s6-arrow").style.width = `${inOut(seg(t, 1.1, 2.0)) * 100}%`;
      document.querySelector(".swap-arrow").style.setProperty("--head", t >= 2.0 ? "#A8D86E" : "rgba(255,255,255,0.1)");
      const o = seg(t, 1.9, 2.5);
      $("s6-out").style.opacity = out3(o);
      $("s6-out").style.transform = `scale(${0.85 + 0.15 * back(o)})`;
      $("s6-slots").style.opacity = out3(seg(t, 2.4, 3.0));
      // slot axis spans commit-10 .. swap+10
      const lo = D.commit.slot - 10, hi = D.swap.slot + 10;
      const x = (s) => ((s - lo) / (hi - lo)) * 100;
      $("s6-m1").style.left = `${x(D.commit.slot)}%`;
      $("s6-m2").style.left = `${x(D.swap.slot)}%`;
      $("s6-m1").style.opacity = out3(seg(t, 2.5, 2.9));
      $("s6-m2").style.opacity = out3(seg(t, 2.9, 3.3));
      const st = $("s6-stamp");
      const sp = seg(t, 3.4, 3.9);
      st.style.opacity = out3(sp);
      st.style.transform = `translateX(-50%) scale(${1.2 - 0.2 * out3(sp)})`;
    },
    s7(t) {
      show($("s7-cap"), out3(seg(t, 0, 0.7)));
      show($("s7-timer"), out3(seg(t, 0.3, 0.9)), 40);
      const run = inOut(seg(t, 0.8, 2.8));
      const secs = Math.round(run * 900);
      $("s7-clock").textContent = `${String(Math.floor(secs / 60)).padStart(2, "0")}:${String(secs % 60).padStart(2, "0")}`;
      $("s7-arc").style.strokeDashoffset = `${540.35 * (1 - run)}`;
      const done = t >= 2.8;
      $("s7-clock").style.color = done ? "#A8D86E" : "#fff";
      show($("s7-exit"), out3(seg(t, 2.9, 3.5)), 16);
      show($("s7-reveal"), out3(seg(t, 3.7, 4.3)), 40);
      const hp = seg(t, 4.5, 5.9);
      $("s7-hash").innerHTML = `<span class="ok">${lines(typed(D.digest, hp), 4)}</span>`;
      const m = seg(t, 6.0, 6.5);
      const match = $("s7-match");
      match.style.opacity = out3(m);
      match.querySelector(".okdot").style.transform = `scale(${back(m)})`;
    },
    s8(t) {
      show($("s8-cap"), out3(seg(t, 0, 0.6)));
      show($("s8-card"), out3(seg(t, 0.2, 0.8)), 40);
      // the edit: select the entry, then type a lower "entry" to fake a better trade
      const orig = T.entry, fake = D.tampered.entry;
      const e = $("s8-entry");
      if (t < 1.3) e.innerHTML = orig;
      else if (t < 1.7) e.innerHTML = `<span class="edit">${orig}</span>`;
      else {
        const p = seg(t, 1.7, 2.6);
        e.innerHTML = `<span class="edit">${typed(fake, p)}</span>${p < 1 ? cursor : ""}`;
      }
      const changed = t >= 2.6;
      const h = changed ? D.tampered.digest : D.digest;
      const hp = changed ? seg(t, 2.6, 3.4) : 1;
      const shown = h.slice(0, Math.round(64 * hp));
      $("s8-hash").innerHTML = changed ? `<span class="bad">${lines(shown, 4)}</span>` : `<span class="ok">${lines(D.digest, 4)}</span>`;
      const b = seg(t, 3.5, 4.1);
      const bad = $("s8-bad");
      bad.style.opacity = out3(b);
      bad.style.transform = `scale(${0.8 + 0.2 * back(b)})`;
    },
    s9(t) {
      const p = seg(t, 0.1, 0.9);
      $("s9-seal").style.opacity = out3(p);
      $("s9-seal").style.transform = `scale(${0.7 + 0.3 * back(p)})`;
      show($("s9-cap"), out3(seg(t, 0.4, 1.2)), 40);
      show($("s9-links"), out3(seg(t, 1.2, 1.9)), 20);
    },
  };

  window.renderFrame = (n) => {
    const t = n / FPS;
    for (const [id, a, b] of SCENES) {
      const el = $(id);
      const first = a === 0, last = b === TOTAL;
      const fin = first ? 1 : seg(t, a - FADE / 2, a + FADE / 2);
      const fout = last ? 1 : 1 - seg(t, b - FADE / 2, b + FADE / 2);
      const op = Math.min(fin, fout);
      el.style.opacity = op;
      el.style.visibility = op > 0 ? "visible" : "hidden";
      if (op > 0) S[id](t - a);
    }
    // chrome: small logo from scene 2 on; data tag over the Oath #2 scenes; fade to black in the last 0.4 s
    $("chrome-logo").style.opacity = clamp(seg(t, 5, 5.6) - seg(t, 56, 56.5));
    $("chrome-tag").style.opacity = clamp(seg(t, 12, 12.6) - seg(t, 56, 56.5));
    $("progress").firstElementChild.style.width = `${(t / TOTAL) * 100}%`;
    $("glow").style.opacity = 0.7 + 0.3 * Math.sin(t * 1.2);
    document.getElementById("stage").style.opacity = t < 0.4 ? seg(t, 0, 0.4) : t > TOTAL - 0.4 ? seg(TOTAL - t, 0, 0.4) : 1;
    return t;
  };
  window.TOTAL_FRAMES = TOTAL * FPS;
  window.renderFrame(Number(new URLSearchParams(location.search).get("f") || 0));
})();
