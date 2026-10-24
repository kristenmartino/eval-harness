import Link from "next/link";

export const metadata = {
  title: "Results status — Eval Harness",
  description: "Production-corpus evaluation has not run. No model rankings or measured cost comparisons are published.",
};

export default function LeaderboardPage() {
  return (
    <article className="mx-auto max-w-6xl px-6 md:px-10 py-16 md:py-24 prose-mdx">
      <div className="mb-4 font-mono text-[var(--text-caption)] tracking-[var(--tracking-mono)] uppercase text-[var(--color-signal-blue-soft)]">
        Production evaluation pending
      </div>
      <h1>Results status</h1>
      <p>
        No model rankings are available. The production-corpus comparison has
        not run, so quality, latency, cost, and routing recommendations remain
        unmeasured.
      </p>

      <h2>What runs today</h2>
      <p>
        Categorization and summarization examples, unit and regression tests,
        and three scripted agent scenarios. The agent fixtures cover retrieval,
        a transient search failure, and an instruction injected into retrieved
        text. These are harness checks, not live-model benchmark results.
      </p>

      <h2>Before a comparison can be published</h2>
      <ul>
        <li>Collect and validate the Sift corpus; prepare and lock the held-out sets.</li>
        <li>Implement the extraction and Task D benchmark modules and complete annotations.</li>
        <li>Pin model snapshots, measure local throughput, and calibrate the judges.</li>
        <li>Run the models and publish quality, latency, and cost with their assumptions and uncertainty.</li>
      </ul>

      <p>
        The <Link href="/methodology">methodology</Link> describes implemented
        scoring and the proposed study. The <Link href="/executive-summary">project summary</Link>{" "}
        lists the current scope.
      </p>
    </article>
  );
}
