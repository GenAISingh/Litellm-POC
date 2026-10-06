import {
  Cpu, Server, Coins, Gauge, Hash, Route, Sparkles, AlertTriangle, ArrowRight,
} from "lucide-react";

function Stat({ icon: Icon, label, value, sub }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-border/50 bg-background/40 px-3.5 py-3">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.1em] text-muted-foreground font-semibold">
        <Icon size={12} />
        {label}
      </div>
      <div className="text-sm font-semibold text-foreground leading-tight">{value}</div>
      {sub && <div className="text-[11px] text-muted-foreground leading-tight">{sub}</div>}
    </div>
  );
}

export default function RoutingPanel() {
  const p = props || {};

  return (
    <div className="routing-card w-full rounded-2xl border border-border bg-card/50 overflow-hidden shadow-sm">
      {/* header */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-5 py-3.5 border-b border-border/60 bg-muted/15">
        <Route size={15} className="text-indigo-400 shrink-0" />
        <span className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground font-semibold">
          Routing trace
        </span>
        <span className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
          <Server size={13} />
          served by
          <span className="font-semibold text-foreground">{p.servedBy || "?"}</span>
        </span>
      </div>

      <div className="px-5 py-5 space-y-4">
        {/* requested → served */}
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <Cpu size={14} /> requested
          </span>
          <span className="font-mono text-foreground font-semibold">{p.requested || "?"}</span>
          {(p.servedModel || p.adaptive) && (
            <>
              <ArrowRight size={13} className="text-muted-foreground/50" />
              <span className="flex items-center gap-1.5 text-muted-foreground">
                {p.adaptive ? <Sparkles size={13} /> : <Cpu size={13} />}
                {p.adaptive ? "adaptive picked" : "served by model"}
              </span>
              <span className="font-mono text-foreground font-semibold">
                {p.adaptive || p.servedModel}
              </span>
            </>
          )}
        </div>

        {/* stat tiles */}
        <div className="grid grid-cols-3 gap-3">
          <Stat
            icon={Hash}
            label="Tokens"
            value={p.tokensTotal ?? "?"}
            sub={`in ${p.tokensIn ?? "?"} · out ${p.tokensOut ?? "?"}`}
          />
          <Stat icon={Coins} label="Cost" value={p.costValue || "—"} sub={p.costSub} />
          <Stat icon={Gauge} label="Latency" value={p.latency || "—"} />
        </div>

        {/* budget warning */}
        {p.budget && (
          <div className="flex items-start gap-2 rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-2.5 text-sm text-amber-200/90">
            <AlertTriangle size={15} className="text-amber-400 shrink-0 mt-0.5" />
            <span>{p.budget}</span>
          </div>
        )}
      </div>
    </div>
  );
}
