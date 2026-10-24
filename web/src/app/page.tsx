import Link from "next/link";
import { categorizationBaseline as baseline } from "@/content/categorization";

export default function HomePage() {
  return (
    <div className="mx-auto max-w-6xl px-6 md:px-10 py-20 md:py-32">
      <div className="mb-6 font-mono text-[var(--text-caption)] tracking-[var(--tracking-mono)] uppercase text-[var(--color-signal-blue-soft)]">
        First development agreement baseline &middot; October 24, 2026
      </div>

      <h1
        className="font-semibold text-[var(--color-bone)] mb-8 max-w-5xl"
        style={{
          fontSize: "var(--text-display)",
          letterSpacing: "var(--tracking-display)",
          lineHeight: "var(--leading-display)",
        }}
      >
        Compare models on Sift&apos;s news-processing tasks.
      </h1>

      <p className="text-lg md:text-xl leading-relaxed text-[var(--color-graphite-20)] max-w-3xl mb-6">
        A Python evaluation harness with categorization and summarization tasks,
        model adapters, and scripted agent regression tests. Built to support
        a future comparison of local models and API models for Sift.
      </p>

      <p className="text-base md:text-lg leading-relaxed text-[var(--color-graphite-40)] max-w-3xl mb-12">
        First result: Llama 3.1 8B matched {(baseline.agreement * 100).toFixed(1)}%
        {" "}of Sift&apos;s stored category labels on {baseline.n_scored} real
        development articles, with macro-F1 {baseline.macro_f1.toFixed(4)}.
        These labels are model-assigned and have not been independently
        reviewed by humans. The {baseline.corpus.reserved_holdout}-item holdout remains unevaluated.
      </p>

      <div className="flex flex-wrap gap-4 mb-20">
        <Link
          href="/leaderboard"
          className="px-5 py-3 bg-[var(--color-signal-blue)] text-[var(--color-bone)] hover:bg-[var(--color-signal-blue-deep)] transition-colors font-mono text-[var(--text-small)] tracking-[var(--tracking-mono-tight)] uppercase"
        >
          View development baseline &rarr;
        </Link>
        <Link
          href="/methodology"
          className="px-5 py-3 border border-[var(--color-graphite-80)] text-[var(--color-bone)] hover:border-[var(--color-graphite-40)] transition-colors font-mono text-[var(--text-small)] tracking-[var(--tracking-mono-tight)] uppercase"
        >
          Methodology
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-[var(--color-graphite-90)] border border-[var(--color-graphite-90)] max-w-5xl">
        <FeatureCell
          label="Categorization development baseline"
          value={`${(baseline.agreement * 100).toFixed(1)}% stored-label agreement`}
          detail={`${baseline.matched}/${baseline.n_scored} labels matched across ten reference categories. This measures agreement with existing model-assigned labels, not human-validated accuracy.`}
        />
        <FeatureCell
          label="Agent regression tests"
          value="Three scripted scenarios"
          detail="Replay fixtures exercise retrieval, a transient tool failure, and a document injection. They test the harness; they do not measure a live model's reliability."
        />
        <FeatureCell
          label="Study status"
          value={`${baseline.corpus.reserved_holdout} held out`}
          detail="The reserved set is unevaluated. Independent label review, a final held-out comparison, more model runs, and measured costs remain pending."
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
            &nbsp;&mdash; implemented scoring, study design, and limitations.
          </li>
          <li>
            <Link
              href="/leaderboard"
              className="text-[var(--color-signal-blue-soft)] underline underline-offset-4 decoration-[var(--color-graphite-80)] hover:decoration-[var(--color-signal-blue)]"
            >
              Development results
            </Link>
            &nbsp;&mdash; measured categorization agreement, sample scope,
            category breakdown, and a downloadable aggregate artifact.
          </li>
          <li>
            <Link
              href="/executive-summary"
              className="text-[var(--color-signal-blue-soft)] underline underline-offset-4 decoration-[var(--color-graphite-80)] hover:decoration-[var(--color-signal-blue)]"
            >
              Executive summary
            </Link>
            &nbsp;&mdash; what is built and what remains to run.
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
