import { useState } from "react";
import {
  Brain, Target, TrendingUp, Compass, Tag, Scale, Coins, ListOrdered, Copy, HeartPulse,
  MessageSquare, Check, ArrowRight, Sparkles, Lightbulb,
} from "lucide-react";

const ICONS = {
  complexity: Brain, quality: Target, adaptive: TrendingUp,
  semantic: Compass, tag: Tag, load: Scale, budget: Coins,
  priority: ListOrdered, mirror: Copy, health: HeartPulse,
};

const CHIP = {
  SIMPLE: "text-teal-300 bg-teal-500/15 border-teal-500/30",
  MEDIUM: "text-blue-300 bg-blue-500/15 border-blue-500/30",
  COMPLEX: "text-violet-300 bg-violet-500/15 border-violet-500/30",
  REASONING: "text-amber-300 bg-amber-500/15 border-amber-500/30",
  FREE: "text-emerald-300 bg-emerald-500/15 border-emerald-500/30",
  PAID: "text-amber-300 bg-amber-500/15 border-amber-500/30",
  CODING: "text-violet-300 bg-violet-500/15 border-violet-500/30",
  CHAT: "text-teal-300 bg-teal-500/15 border-teal-500/30",
  OK: "text-emerald-300 bg-emerald-500/15 border-emerald-500/30",
  OVER: "text-rose-300 bg-rose-500/15 border-rose-500/30",
  FASTEST: "text-emerald-300 bg-emerald-500/15 border-emerald-500/30",
  SLOWER: "text-slate-300 bg-slate-500/15 border-slate-500/30",
  PRIMARY: "text-blue-300 bg-blue-500/15 border-blue-500/30",
  BACKUP: "text-amber-300 bg-amber-500/15 border-amber-500/30",
  ANSWER: "text-blue-300 bg-blue-500/15 border-blue-500/30",
  SHADOW: "text-violet-300 bg-violet-500/15 border-violet-500/30",
  HEALTHY: "text-emerald-300 bg-emerald-500/15 border-emerald-500/30",
  UNHEALTHY: "text-rose-300 bg-rose-500/15 border-rose-500/30",
};

function SectionLabel({ children, hint }) {
  return (
    <div className="flex items-baseline justify-between mb-4">
      <span className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground font-semibold">
        {children}
      </span>
      {hint && <span className="text-[11px] text-muted-foreground/70">{hint}</span>}
    </div>
  );
}

export default function StrategyCard() {
  const strategies = props.strategies || [];
  const [active, setActive] = useState(props.active || (strategies[0] && strategies[0].id));
  const s = strategies.find((x) => x.id === active) || strategies[0];
  if (!s) return null;

  const select = (st) => {
    setActive(st.id);
    if (st.model) callAction({ name: "pick_model", payload: { model: st.model } });
  };
  const runExample = async (ex) => {
    if (s.model) await callAction({ name: "pick_model", payload: { model: s.model } });
    sendUserMessage(ex);
  };

  const ActiveIcon = ICONS[s.icon] || Brain;

  return (
    <div className="w-full rounded-2xl border border-border bg-card/50 overflow-hidden shadow-sm">
      {/* ── Header: title + strategy tabs ───────────────────────── */}
      <div className="px-5 pt-5 pb-4 border-b border-border/60 bg-muted/10">
        <div className="flex items-center gap-2 mb-4">
          <Sparkles size={15} className="text-indigo-400" />
          <span className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground font-semibold">
            Routing strategy
          </span>
        </div>

        <div className="flex flex-wrap gap-2">
          {strategies.map((st) => {
            const Icon = ICONS[st.icon] || Brain;
            const on = st.id === active;
            return (
              <button
                key={st.id}
                onClick={() => select(st)}
                className={
                  "flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition " +
                  (on
                    ? "border-indigo-400/70 bg-indigo-500/15 text-foreground shadow-sm"
                    : "border-border/70 text-muted-foreground hover:text-foreground hover:bg-muted/60 hover:border-border")
                }
              >
                <Icon size={15} className={on ? "text-indigo-400" : ""} />
                {st.tab}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Body ────────────────────────────────────────────────── */}
      <div className="px-5 py-7 space-y-9">
        {/* active strategy heading */}
        <div className="flex items-center gap-3 pb-6 border-b border-border/50">
          <span className="flex items-center justify-center w-10 h-10 rounded-xl bg-indigo-500/15 text-indigo-400 shrink-0">
            <ActiveIcon size={20} />
          </span>
          <div className="flex flex-col gap-1 leading-tight">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-base font-semibold text-foreground">{s.tab}</span>
              {s.tag && (
                <span className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
                  {s.tag}
                </span>
              )}
            </div>
            {s.model && (
              <span className="font-mono text-xs text-indigo-400">{s.model}</span>
            )}
          </div>
        </div>

        {/* why use it — the headline for a single-glance read */}
        {s.why && (
          <div className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3">
            <Lightbulb size={17} className="text-amber-400 shrink-0 mt-0.5" />
            <div>
              <div className="text-[11px] uppercase tracking-[0.12em] text-amber-300/90 font-semibold mb-1">
                Why use it
              </div>
              <p className="text-sm text-foreground/90 leading-relaxed">{s.why}</p>
            </div>
          </div>
        )}

        {/* how it routes */}
        <div>
          <SectionLabel>How it routes</SectionLabel>
          <p className="text-sm text-foreground/90 leading-relaxed rounded-xl border border-border/50 bg-muted/15 px-4 py-3">
            {s.how}
          </p>
        </div>

        {/* routes among — visual flow */}
        <div>
          <SectionLabel hint={s.routes && s.routes.length ? `${s.routes.length} routes` : null}>
            Routes &amp; destinations
          </SectionLabel>
          <div className="flex flex-col gap-2">
            {(s.routes || []).map((r, i) => (
              <div
                key={i}
                className="flex items-center gap-3 rounded-lg border border-border/50 bg-background/40 px-3 py-2.5 hover:border-border hover:bg-muted/30 transition"
              >
                <span
                  className={
                    "text-[10px] font-bold tracking-wide px-2.5 py-1 rounded-md border w-24 text-center shrink-0 " +
                    (CHIP[r[0]] || "text-muted-foreground border-border")
                  }
                >
                  {r[0]}
                </span>
                <ArrowRight size={14} className="text-muted-foreground/50 shrink-0" />
                <span className="font-mono text-sm text-foreground font-semibold truncate">{r[1]}</span>
                <span className="ml-auto text-xs text-muted-foreground text-right shrink-0 pl-2">{r[2]}</span>
              </div>
            ))}
          </div>
        </div>

        {/* examples */}
        {s.examples && s.examples.length > 0 && (
          <div>
            <SectionLabel hint="click to run live">Try an example</SectionLabel>
            <div className="grid grid-cols-1 gap-2">
              {s.examples.map((ex, i) => (
                <button
                  key={i}
                  onClick={() => runExample(ex)}
                  className="group flex items-center gap-3 rounded-lg border border-border/60 bg-muted/20 px-3.5 py-3 text-sm text-foreground/80 hover:border-indigo-400/60 hover:bg-indigo-500/5 hover:text-foreground text-left transition"
                >
                  <MessageSquare size={15} className="text-muted-foreground group-hover:text-indigo-400 shrink-0 transition" />
                  <span className="flex-1">{ex}</span>
                  <ArrowRight size={14} className="text-muted-foreground/0 group-hover:text-indigo-400 shrink-0 transition" />
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Footer status ───────────────────────────────────────── */}
      <div className="px-5 py-3 border-t border-border/60 bg-muted/20 flex items-center gap-2 text-xs text-muted-foreground">
        <Check size={14} className="text-emerald-400 shrink-0" />
        <span>
          Active router:{" "}
          <span className="font-mono text-foreground">{s.model || "—"}</span>
          {" "}— type below or click an example to run it.
        </span>
      </div>
    </div>
  );
}
