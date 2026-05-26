import Link from "next/link";

export default function HomePage() {
  return (
    <div className="mx-auto max-w-6xl px-6 md:px-10 py-20 md:py-32">
      <div className="mb-6 font-mono text-[var(--text-caption)] tracking-[var(--tracking-mono)] uppercase text-[var(--color-signal-blue-soft)]">
        Pre-execution scoping &middot; Phase 1 in progress
      </div>

      <h1
        className="font-semibold text-[var(--color-bone)] mb-8 max-w-5xl"
        style={{
          fontSize: "var(--text-display)",
          letterSpacing: "var(--tracking-display)",
          lineHeight: "var(--leading-display)",
        }}
      >
        Open-weight vs frontier LLMs, evaluated on a real production workload.
      </h1>

      <p className="text-lg md:text-xl leading-relaxed text-[var(--color-graphite-20)] max-w-3xl mb-6">
        A defensible cost/quality leaderboard comparing 5 open-weight models
        (Llama, Qwen, DeepSeek &mdash; on a local DGX Spark via Ollama) against
        4 frontier APIs (Anthropic + OpenAI) on Sift&apos;s production news
        pipeline.
      </p>

      <p className="text-base md:text-lg leading-relaxed text-[var(--color-graphite-40)] max-w-3xl mb-12">
        Four tasks. Held-out discipline that&apos;s verifiable from the
        commit history. Cross-vendor judging to control for self-preference
        bias. Hardware-amortized cost methodology.
      </p>

      <div className="flex flex-wrap gap-4 mb-20">
        <Link
          href="/methodology"
          className="px-5 py-3 bg-[var(--color-signal-blue)] text-[var(--color-bone)] hover:bg-[var(--color-signal-blue-deep)] transition-colors font-mono text-[var(--text-small)] tracking-[var(--tracking-mono-tight)] uppercase"
        >
          Read the methodology &rarr;
        </Link>
        <Link
          href="/executive-summary"
          className="px-5 py-3 border border-[var(--color-graphite-80)] text-[var(--color-bone)] hover:border-[var(--color-graphite-40)] transition-colors font-mono text-[var(--text-small)] tracking-[var(--tracking-mono-tight)] uppercase"
        >
          Executive summary
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-[var(--color-graphite-90)] border border-[var(--color-graphite-90)] max-w-5xl">
        <FeatureCell
          label="Methodology"
          value="Cross-vendor judging"
          detail="Sonnet 4.6 judges non-Anthropic pairs; GPT-4o judges Anthropic pairs. 50-pair calibration overlap with Cohen's κ ≥ 0.6 floor."
        />
        <FeatureCell
          label="Reproducibility"
          value="Verifiable held-out"
          detail="20% held-out set SHA-256 hashed pre-iteration. Hash committed to git before any prompt tuning. Anyone can verify the bound wasn't crossed."
        />
        <FeatureCell
          label="Cost model"
          value="Hardware-amortized"
          detail="Real DGX Spark capex + Florida kWh + utilization vs. published API rates. Dual-view: individual developer cost vs. fully-loaded production cost."
        />
      </div>

      <div className="mt-16 max-w-3xl">
        <h2
          className="font-semibold text-[var(--color-bone)] mb-4"
          style={{
            fontSize: "var(--text-h3)",
            letterSpacing: "var(--tracking-tight)",
          }}
        >
          What&apos;s on this site
        </h2>
        <ul className="space-y-3 text-base md:text-lg leading-relaxed text-[var(--color-graphite-20)]">
          <li>
            <Link
              href="/methodology"
              className="text-[var(--color-signal-blue-soft)] underline underline-offset-4 decoration-[var(--color-graphite-80)] hover:decoration-[var(--color-signal-blue)]"
            >
              Methodology
            </Link>
            &nbsp;&mdash; full study design, scoring, statistical treatment,
            and cost model. The substantive page.
          </li>
          <li>
            <Link
              href="/leaderboard"
              className="text-[var(--color-signal-blue-soft)] underline underline-offset-4 decoration-[var(--color-graphite-80)] hover:decoration-[var(--color-signal-blue)]"
            >
              Leaderboard
            </Link>
            &nbsp;&mdash; results land at the end of Phase 1. Placeholder for
            now with the planned shape.
          </li>
          <li>
            <Link
              href="/executive-summary"
              className="text-[var(--color-signal-blue-soft)] underline underline-offset-4 decoration-[var(--color-graphite-80)] hover:decoration-[var(--color-signal-blue)]"
            >
              Executive summary
            </Link>
            &nbsp;&mdash; one-pager for hiring managers and senior reviewers.
          </li>
        </ul>
      </div>
    </div>
  );
}

function FeatureCell({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="bg-[var(--color-soot)] p-6 md:p-8">
      <div className="font-mono text-[var(--text-caption)] tracking-[var(--tracking-mono)] uppercase text-[var(--color-graphite-40)] mb-3">
        {label}
      </div>
      <div className="text-[var(--text-lead)] font-semibold text-[var(--color-bone)] mb-2 leading-snug">
        {value}
      </div>
      <p className="text-[var(--text-small)] leading-relaxed text-[var(--color-graphite-40)]">
        {detail}
      </p>
    </div>
  );
}
