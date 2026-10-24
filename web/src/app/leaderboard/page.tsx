import Link from "next/link";
import { categorizationBaseline as baseline, categorizationResultsUrl } from "@/content/categorization";
import { site } from "@/content/site";

export const metadata = {
  title: "Categorization development agreement baseline — Eval Harness",
  description: "Llama 3.1 8B on 400 development articles: 79.8% agreement with existing model-assigned Sift labels, macro-F1 0.7598. Human label validation remains pending.",
};

export default function LeaderboardPage() {
  return (
    <article className="mx-auto max-w-6xl px-6 md:px-10 py-16 md:py-24 prose-mdx baseline-results">
      <div className="mb-4 font-mono text-[var(--text-caption)] tracking-[var(--tracking-mono)] uppercase text-[var(--color-signal-blue-soft)]">
        Development agreement baseline &middot; October 24, 2026
      </div>
      <h1>Categorization results</h1>
      <p>
        {baseline.model.name} completed {baseline.n_scored} real development
        articles across {baseline.n_reference_categories}{" "}reference categories.
        This first run measures agreement with Sift&apos;s stored labels.
      </p>

      <aside aria-label="How to interpret these results" className="my-8 max-w-3xl border-l-2 border-[var(--color-signal-blue)] bg-[var(--color-graphite-90)] p-5">
        <p className="mb-0">
          <strong>The reference labels are model-assigned and have not been independently reviewed by humans.</strong>
          {" "}Agreement is not yet a measure of validated classification accuracy.
          The {baseline.corpus.reserved_holdout}-item holdout remains reserved and unevaluated.
        </p>
      </aside>

      <dl className="my-10 grid grid-cols-1 sm:grid-cols-2 gap-6 max-w-4xl">
        <div>
          <dt className="text-[var(--color-graphite-40)]">Stored-label agreement</dt>
          <dd className="text-3xl font-semibold my-2">{(baseline.agreement * 100).toFixed(1)}%</dd>
          <dd>{baseline.matched} of {baseline.n_scored} labels matched</dd>
        </div>
        <div>
          <dt className="text-[var(--color-graphite-40)]">Macro-F1 against stored labels</dt>
          <dd className="text-3xl font-semibold my-2">{baseline.macro_f1.toFixed(4)}</dd>
          <dd>Descriptive 95% bootstrap interval: {baseline.macro_f1_interval.low.toFixed(4)}–{baseline.macro_f1_interval.high.toFixed(4)}</dd>
        </div>
        <div>
          <dt className="text-[var(--color-graphite-40)]">Execution coverage</dt>
          <dd className="text-3xl font-semibold my-2">{baseline.n_scored}/{baseline.n_scored}</dd>
          <dd>0 errors, 0 retries, 0 parse failures</dd>
        </div>
        <div>
          <dt className="text-[var(--color-graphite-40)]">Reserved holdout</dt>
          <dd className="text-3xl font-semibold my-2">{baseline.corpus.reserved_holdout} articles</dd>
          <dd>Not used in this development run</dd>
        </div>
      </dl>

      <h2>Per-category agreement</h2>
      <p>
        Every row compares the model&apos;s output with the stored category.
        The largest disagreement pairs were <code>world → politics</code> (14)
        and <code>general → politics</code> (10). These cases have not been adjudicated.
      </p>
      <div className="overflow-x-auto mb-6" role="region" aria-label="Per-category agreement table" tabIndex={0}>
        <table>
          <caption className="sr-only">Development agreement by stored category</caption>
          <thead><tr>
            <th scope="col">Stored category</th><th scope="col">Items</th>
            <th scope="col">Matches</th><th scope="col">F1 vs stored labels</th>
          </tr></thead>
          <tbody>{baseline.per_category.map((row) => (
            <tr key={row.category}>
              <th scope="row">{row.category}</th><td>{row.support}</td>
              <td>{row.matched}</td><td>{row.f1_vs_stored_labels.toFixed(3)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <p>Energy has only 16 development items; its class-level estimate is particularly uncertain.</p>

      <h2>Sample and scope</h2>
      <p>
        From {baseline.corpus.unique_source_matched_inputs} unique source-matched
        inputs, a fixed-seed stratified sample selected {baseline.corpus.selected}
        {" "}articles: {baseline.corpus.development} development and {baseline.corpus.reserved_holdout}
        {" "}reserved holdout. Original RSS titles, sources, and bodies were
        matched to a read-only snapshot of production labels. Generated
        summaries and stored category fields were excluded from article input.
      </p>
      <ul>
        <li>55 outlets; 205 fresh-capture and 195 saved original inputs, published October 10, 2024–October 24, 2026. This is not a random recent-production sample.</li>
        <li><code>top</code> had only 14 unique captured inputs, below the 20-item minimum, and was excluded from reference sampling. All eleven Sift labels remained valid outputs; macro-F1 uses the ten sampled reference categories. All 400 development items are counted.</li>
        <li>A disagreement may reflect a model error, a noisy stored label, or an ambiguous category boundary. Independent label review is still needed.</li>
        <li>One development run does not establish a model ranking or justify a production routing change. Final held-out and cost comparisons remain pending.</li>
      </ul>

      <details className="my-8 max-w-4xl">
        <summary className="cursor-pointer text-[var(--color-signal-blue-soft)]">Runtime and provenance</summary>
        <p className="mt-5">
          Local macOS ARM64, Ollama {baseline.runtime.ollama_version}; temperature {baseline.sampling.temperature},
          seed {baseline.sampling.seed}, maximum {baseline.sampling.max_output_tokens} output tokens.
          The categorization-only prompt uses Sift&apos;s checked-out category rules,
          rather than the production batch summarization operation.
        </p>
        <p>
          Median generation HTTP latency: {(baseline.runtime.generation_http_latency_ms.p50 / 1000).toFixed(3)}s;
          p95: {(baseline.runtime.generation_http_latency_ms.p95 / 1000).toFixed(3)}s.
          These timings exclude the separate digest check and are not a DGX Spark
          benchmark or a measured cost comparison.
        </p>
        <p>
          The Ollama manifest was checked before each generation. Its SHA-256 is
          <code className="break-all"> {baseline.model.artifact_sha256}</code>.
          This identifies the Ollama artifact; no Hugging Face commit is asserted.
        </p>
        <p>
          The run started from commit <code>{baseline.provenance.base_git_commit.slice(0, 7)}</code>
          {" "}with uncommitted run-enablement changes. Executed sources were snapshotted
          and hashed; that base commit alone is not the complete run code. Matching
          source files and hashes are published with this baseline. Article text
          and per-item artifacts remain local.
        </p>
      </details>
      <p>
        <a href={categorizationResultsUrl} download>Download aggregate results and provenance (JSON)</a>
        {" · "}<a href={`${site.repoUrl}/blob/main/docs/results/2026-10-24-categorization-development.md`}>Read the run report</a>
      </p>
      <p>
        See the <Link href="/methodology">methodology</Link> and <Link href="/executive-summary">project summary</Link>
        {" "}for scoring and the broader study. Agent scenarios remain scripted
        fixtures, separate from this real categorization run.
      </p>
    </article>
  );
}
