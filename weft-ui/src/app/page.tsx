import {
  Activity,
  AlertTriangle,
  BookOpen,
  Brain,
  CheckCircle2,
  FileText,
  MemoryStick,
  PenLine,
  Radio,
  Search,
  Sparkles,
  Wifi,
  Zap,
} from "lucide-react";

const researcherThoughts = [
  {
    time: "14:02:11",
    text: "Indexing competitor filings for FY market share.",
  },
  {
    time: "14:02:14",
    text: "Composite index: Northwind holds 18.4% of seats.",
  },
  {
    time: "14:02:16",
    text: "Source is Q3 2023. Calendar is Q3 2026 — 11 quarters stale.",
  },
  {
    time: "14:02:17",
    text: "Emitting STALE_SOURCE to Moss shared memory.",
  },
];

export default function Home() {
  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-zinc-950 text-zinc-100">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-zinc-800/80 bg-zinc-950 px-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-zinc-100 text-zinc-950">
            <Sparkles className="h-3.5 w-3.5" strokeWidth={2.25} />
          </div>
          <div className="flex min-w-0 items-center gap-2">
            <span className="text-[13px] font-semibold tracking-tight">
              Weft
            </span>
            <span className="text-zinc-600">/</span>
            <span className="truncate text-[13px] text-zinc-400">
              Competitive Analysis
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-300">
            <span className="relative flex h-1.5 w-1.5">
              <span className="live-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
            </span>
            Live session
          </span>
          <span className="hidden items-center gap-1 rounded-full border border-zinc-800 bg-zinc-900 px-2.5 py-1 text-[11px] text-zinc-400 sm:inline-flex">
            <Wifi className="h-3 w-3" />
            3 agents
          </span>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <main className="flex min-h-0 w-[65%] min-w-0 flex-col">
          <div className="flex h-10 shrink-0 items-center justify-between border-b border-zinc-800/70 bg-zinc-900/40 px-5">
            <div className="flex items-center gap-2 text-[12px] text-zinc-400">
              <FileText className="h-3.5 w-3.5 text-zinc-500" />
              <span>Canvas</span>
            </div>
            <span className="inline-flex items-center gap-1.5 rounded-md bg-zinc-900 px-2 py-0.5 font-mono text-[10px] text-zinc-400 ring-1 ring-zinc-800">
              <PenLine className="h-3 w-3 text-sky-400" />
              Streaming
            </span>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto">
            <article className="mx-auto w-full max-w-2xl px-6 py-10 sm:px-10 sm:py-12">
              <p className="mb-3 text-[11px] font-medium uppercase tracking-[0.18em] text-zinc-500">
                Draft · synced with Moss
              </p>
              <h1 className="text-[1.85rem] font-semibold tracking-tight text-zinc-50 sm:text-[2.05rem]">
                Competitive Analysis Report
              </h1>
              <p className="mt-2 text-sm text-zinc-500">
                Enterprise collaboration software · North America · 2026
              </p>

              <div className="mt-8 space-y-5 text-[15px] leading-7 text-zinc-300">
                <h2 className="text-base font-semibold tracking-tight text-zinc-100">
                  1. Executive summary
                </h2>
                <p>
                  The collaboration suite market remains concentrated around
                  three platforms. Weft&apos;s positioning depends on real-time
                  agent coordination rather than document storage alone.
                </p>

                <h2 className="pt-2 text-base font-semibold tracking-tight text-zinc-100">
                  2. Market share
                </h2>

                <div className="rounded-lg border border-red-500/20 bg-red-950/20 px-3.5 py-3">
                  <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-red-300/90">
                    <AlertTriangle className="h-3 w-3" />
                    Obsolete block · aborted by Moss
                  </div>
                  <p className="text-[14px] leading-6 text-zinc-500 line-through decoration-zinc-600">
                    Northwind retains an 18.4% share of seats, per the Q3 2023
                    composite index. Aurora follows at 12.1%. Recommend building
                    the GTM plan against this 2023 snapshot.
                  </p>
                </div>

                <p>
                  <span className="rounded-sm bg-amber-400/15 px-1 text-amber-200">
                    Pivot 14:02:18
                  </span>{" "}
                  Stale 2023 share figures were discarded after Moss broadcast{" "}
                  <span className="font-mono text-[13px] text-amber-300">
                    ABORT_TASK
                  </span>
                  . Writer is now grounding this section in 2026 primary
                  sources: SEC 10-K filings, G2 category movement, and live
                  pipeline win/loss notes.
                </p>

                <p>
                  Preliminary 2026 replacement: Northwind ~14.9% of paid seats
                  (−3.5 pts), Aurora ~16.2% (now category leader on mid-market
                  expansion). Weft should treat Aurora—not Northwind—as the
                  primary competitive threat this cycle
                  <span className="caret" aria-hidden />
                </p>
              </div>
            </article>
          </div>
        </main>

        <aside className="flex min-h-0 w-[35%] flex-col border-l border-zinc-800 bg-zinc-900">
          <div className="flex h-10 shrink-0 items-center justify-between border-b border-zinc-800 px-3">
            <div className="flex items-center gap-2 text-[12px] font-medium text-zinc-200">
              <Activity className="h-3.5 w-3.5 text-violet-300" />
              The Weft Engine
            </div>
            <span className="font-mono text-[10px] text-zinc-500">
              t+00:00:18
            </span>
          </div>

          <div className="grid min-h-0 flex-1 grid-rows-[auto_auto_minmax(0,1fr)] gap-2.5 overflow-hidden p-2.5">
            <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950/70 p-2.5">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-sky-500/10 text-sky-300 ring-1 ring-sky-500/20">
                    <Search className="h-3.5 w-3.5" />
                  </div>
                  <h3 className="truncate text-[13px] font-semibold text-zinc-100">
                    Researcher Agent
                  </h3>
                </div>
                <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-300 ring-1 ring-amber-500/25">
                  <AlertTriangle className="h-3 w-3" />
                  Stale
                </span>
              </div>

              <ol className="min-h-[4.25rem] space-y-1.5 overflow-y-auto font-mono text-[11px] leading-4 text-zinc-400">
                {researcherThoughts.map((thought, index) => (
                  <li
                    key={thought.time}
                    className="thought-row flex gap-2"
                    style={{ animationDelay: `${index * 80}ms` }}
                  >
                    <span className="shrink-0 text-zinc-600">
                      {thought.time}
                    </span>
                    <span
                      className={
                        index === researcherThoughts.length - 1
                          ? "text-zinc-200"
                          : ""
                      }
                    >
                      {thought.text}
                    </span>
                  </li>
                ))}
              </ol>

              <div className="mt-2 shrink-0 rounded-lg border border-zinc-800 bg-zinc-900/80 px-2.5 py-2">
                <div className="mb-0.5 flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-zinc-500">
                  <BookOpen className="h-3 w-3" />
                  Finding
                </div>
                <p className="text-[11px] leading-4 text-zinc-200">
                  Landscape dataset dated{" "}
                  <span className="font-medium text-red-300">2023-Q3</span> — 11
                  quarters stale. Confidence 0.21.
                </p>
              </div>
            </section>

            <section className="shrink-0 rounded-xl border border-amber-500/40 bg-zinc-950 p-2.5 shadow-[inset_0_1px_0_0_rgb(251_191_36_/_0.14)]">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-amber-500/15 text-amber-300 ring-1 ring-amber-400/30">
                    <MemoryStick className="h-3.5 w-3.5" />
                  </div>
                  <h3 className="truncate text-[13px] font-semibold text-zinc-50">
                    Moss Shared Memory
                  </h3>
                </div>
                <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-400 ring-1 ring-zinc-700">
                  <Brain className="h-3 w-3 text-amber-300" />
                  Live
                </span>
              </div>

              <div className="signal-badge flex items-center justify-between gap-2 rounded-lg border border-amber-400/50 bg-amber-500/15 px-2.5 py-2">
                <div className="flex min-w-0 items-center gap-1.5">
                  <Zap className="h-3.5 w-3.5 shrink-0 text-amber-300" />
                  <p className="truncate text-[11px] font-semibold tracking-wide text-amber-100">
                    SIGNAL: ABORT_TASK
                  </p>
                </div>
                <span className="shrink-0 font-mono text-[10px] text-amber-200/90">
                  2.4ms
                </span>
              </div>
              <p className="mt-2 text-[11px] leading-4 text-zinc-400">
                In-process latency{" "}
                <span className="font-mono text-zinc-200">2.4ms</span>
                {" · "}
                Reason:{" "}
                <span className="text-zinc-200">obsolete data</span>
              </p>
            </section>

            <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950/70 p-2.5">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-violet-500/10 text-violet-300 ring-1 ring-violet-500/20">
                    <PenLine className="h-3.5 w-3.5" />
                  </div>
                  <h3 className="truncate text-[13px] font-semibold text-zinc-100">
                    Writer Agent
                  </h3>
                </div>
                <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-violet-500/10 px-2 py-0.5 text-[10px] font-medium text-violet-300 ring-1 ring-violet-500/25">
                  <Radio className="h-3 w-3" />
                  Pivoting
                </span>
              </div>

              <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto text-[11px] leading-4">
                <div className="flex items-start gap-2 text-zinc-500">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <p>Drafted §2 from the 18.4% Northwind share table.</p>
                </div>
                <div className="flex items-start gap-2 text-amber-200/90">
                  <Zap className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-300" />
                  <p>
                    Moss{" "}
                    <span className="font-mono text-[10px]">ABORT_TASK</span> in
                    2.4ms. Halted mid-sentence.
                  </p>
                </div>
                <div className="flex items-start gap-2 text-zinc-200">
                  <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-violet-300" />
                  <p>
                    Auto-pivot: struck 2023 copy, streaming 2026 filings on the
                    canvas.
                  </p>
                </div>
              </div>
            </section>
          </div>
        </aside>
      </div>
    </div>
  );
}
