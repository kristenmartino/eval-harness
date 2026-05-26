import Link from "next/link";

export const metadata = {
  title: "Leaderboard — Eval Harness",
  description:
    "Results from Phase 1 will land here. Cost/quality Pareto across 9 models on 4 tasks.",
};

export default function LeaderboardPage() {
  return (
    <article className="mx-auto max-w-6xl px-6 md:px-10 py-16 md:py-24 prose-mdx">
      <div className="mb-4 font-mono text-[var(--text-caption)] tracking-[var(--tracking-mono)] uppercase text-[var(--color-signal-blue-soft)]">
        Phase 1 in progress
      </div>

      <h1
        className="font-semibold text-[var(--color-bone)] mb-8 max-w-4xl"
        style={{
          fontSize: "var(--text-h1)",
          letterSpacing: "var(--tracking-display)",
          lineHeight: "var(--leading-tight)",
        }}
      >
        Leaderboard
      </h1>

      <p className="text-lg md:text-xl leading-relaxed text-[var(--color-graphite-20)] max-w-3xl mb-8">
        Results land here at the end of Phase 1. Until then, here&apos;s what
        the leaderboard will show and how to read it.
      </p>

      <h2
        className="font-semibold text-[var(--color-bone)] mt-14 mb-5"
        style={{
          fontSize: "var(--text-h3)",
          letterSpacing: "var(--tracking-tight)",
          lineHeight: "var(--leading-tight)",
        }}
      >
        Planned shape
      </h2>

      <div className="overflow-x-auto max-w-5xl mb-8">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr>
              {[
                "Model",
                "Tier",
                "Task A (cat. F1)",
                "Task B (BT strength)",
                "Task C (JSON F1)",
                "Task D (faith.)",
                "$/1M tok",
                "p95 latency",
              ].map((h) => (
                <th
                  key={h}
                  className="text-left px-3 py-2 font-mono text-[var(--text-meta)] uppercase tracking-[var(--tracking-mono-tight)] text-[var(--color-graphite-40)] border-b border-[var(--color-graphite-80)] font-medium"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="text-[var(--color-graphite-20)]">
            {[
              "Claude Sonnet 4.6",
              "Claude Haiku 4.5",
              "GPT-4o",
              "GPT-4o mini",
              "Llama 3.1 70B Q4",
              "Llama 3.1 8B",
              "Qwen 2.5 14B",
              "Qwen 2.5 7B",
              "DeepSeek R1 distill 8B",
            ].map((m) => (
              <tr key={m} className="border-b border-[var(--color-graphite-90)]">
                <td className="px-3 py-2.5">{m}</td>
                <td className="px-3 py-2.5 text-[var(--color-graphite-60)]">
                  &mdash;
                </td>
                <td className="px-3 py-2.5 text-[var(--color-graphite-60)]">
                  pending
                </td>
                <td className="px-3 py-2.5 text-[var(--color-graphite-60)]">
                  pending
                </td>
                <td className="px-3 py-2.5 text-[var(--color-graphite-60)]">
                  pending
                </td>
                <td className="px-3 py-2.5 text-[var(--color-graphite-60)]">
                  pending
                </td>
                <td className="px-3 py-2.5 text-[var(--color-graphite-60)]">
                  pending
                </td>
                <td className="px-3 py-2.5 text-[var(--color-graphite-60)]">
                  pending
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2
        className="font-semibold text-[var(--color-bone)] mt-14 mb-5"
        style={{
          fontSize: "var(--text-h3)",
          letterSpacing: "var(--tracking-tight)",
          lineHeight: "var(--leading-tight)",
        }}
      >
        How to read this
      </h2>

      <ul className="mb-6 ml-6 list-disc space-y-2 text-base md:text-lg leading-relaxed text-[var(--color-graphite-20)] max-w-3xl marker:text-[var(--color-graphite-60)]">
        <li>
          <span className="text-[var(--color-bone)] font-semibold">Tier</span>{" "}
          splits models into <em className="italic text-[var(--color-bone)]">deployment-feasible</em>{" "}
          vs <em className="italic text-[var(--color-bone)]">quality-ceiling</em>. Llama 70B Q4 on a
          single DGX Spark is a quality reference, not a deployment-ready
          candidate at the throughput Sift needs.
        </li>
        <li>
          <span className="text-[var(--color-bone)] font-semibold">Task A</span> is multi-label
          news categorization. Macro-F1 with bootstrap CI; label noise rate
          computed from a 100-article re-validation pass.
        </li>
        <li>
          <span className="text-[var(--color-bone)] font-semibold">Task B</span> is summarization.
          Bradley-Terry strength across 36 pairwise comparisons, fit with the
          MM algorithm. Cross-vendor judging (see methodology) controls for
          self-preference bias.
        </li>
        <li>
          <span className="text-[var(--color-bone)] font-semibold">Task C</span> is structured
          entity extraction. Two metrics, not one: JSON schema validity rate
          AND entity F1 conditional on validity &mdash; so &ldquo;great
          extractor, dropped a brace&rdquo; isn&apos;t scored the same as
          &ldquo;couldn&apos;t parse the article.&rdquo;
        </li>
        <li>
          <span className="text-[var(--color-bone)] font-semibold">Task D</span> is grounded
          summarization with citation faithfulness on multi-article topic
          clusters.
        </li>
        <li>
          <span className="text-[var(--color-bone)] font-semibold">$/1M tok</span> uses a
          hardware-amortized model for local; published rates for APIs. Dual
          view (individual-developer / fully-loaded production) lives in the
          methodology page.
        </li>
      </ul>

      <div className="mt-12 p-5 border border-[var(--color-graphite-90)] max-w-3xl">
        <div className="font-mono text-[var(--text-caption)] tracking-[var(--tracking-mono)] uppercase text-[var(--color-graphite-40)] mb-2">
          Why this is empty right now
        </div>
        <p className="text-[var(--color-graphite-20)] leading-relaxed text-[var(--text-body)]">
          The methodology is what makes the leaderboard defensible &mdash; not
          the other way around. Phase 0 (scoping, pre-flight, dataset
          construction) is finishing first. Phase 1 produces these numbers
          across one held-out lock and a fully-pinned model set.{" "}
          <Link
            href="/methodology"
            className="text-[var(--color-signal-blue-soft)] underline underline-offset-4 decoration-[var(--color-graphite-80)] hover:decoration-[var(--color-signal-blue)]"
          >
            Read the methodology &rarr;
          </Link>
        </p>
      </div>
    </article>
  );
}
