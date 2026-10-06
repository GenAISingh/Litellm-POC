import { Sparkles, ArrowRight } from "lucide-react";

const CHIP = {
  SIMPLE: "text-teal-300 bg-teal-500/15 border-teal-500/30",
  MEDIUM: "text-blue-300 bg-blue-500/15 border-blue-500/30",
  COMPLEX: "text-violet-300 bg-violet-500/15 border-violet-500/30",
  REASONING: "text-amber-300 bg-amber-500/15 border-amber-500/30",
  SEMANTIC: "text-cyan-300 bg-cyan-500/15 border-cyan-500/30",
};

export default function RouteBanner() {
  const p = props || {};
  const tierCls = CHIP[p.tier] || "text-muted-foreground bg-muted/40 border-border";

  return (
    <div className="routing-card w-full rounded-xl border border-indigo-400/30 bg-indigo-500/[0.06] px-4 py-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
        <Sparkles size={15} className="text-indigo-400 shrink-0" />
        <span className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground font-semibold">
          Routed to
        </span>
        <span className="font-mono text-sm font-semibold text-foreground">{p.model || "?"}</span>
        {p.tier && (
          <span className={"text-[10px] font-bold tracking-wide px-2 py-0.5 rounded-md border " + tierCls}>
            {p.tier}
          </span>
        )}
        {p.provider && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
            via <span className="text-foreground font-medium">{p.provider}</span>
          </span>
        )}
      </div>

      {p.why && (
        <div className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground">
          <ArrowRight size={13} className="text-indigo-400/70 shrink-0 mt-0.5" />
          <span>
            <span className="font-semibold text-foreground/70">Why:</span> {p.why}
          </span>
        </div>
      )}

      {p.router && p.router !== p.model && (
        <div className="mt-1 text-[11px] text-muted-foreground/70 pl-[1.35rem]">
          requested <span className="font-mono">{p.router}</span>
        </div>
      )}
    </div>
  );
}
