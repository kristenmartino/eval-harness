import Link from "next/link";
import { site } from "@/content/site";

export function Footer() {
  return (
    <footer className="border-t border-[var(--color-graphite-90)] mt-24">
      <div className="mx-auto max-w-6xl px-6 md:px-10 py-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="font-mono text-[var(--text-meta)] tracking-[var(--tracking-mono-tight)] uppercase text-[var(--color-graphite-40)]">
          eval-harness &middot; methodology + leaderboard
        </div>
        <div className="flex items-center gap-6 font-mono text-[var(--text-meta)] tracking-[var(--tracking-mono-tight)] uppercase">
          <Link
            href={site.portfolioUrl}
            target="_blank"
            rel="noreferrer"
            className="text-[var(--color-graphite-40)] hover:text-[var(--color-bone)] transition-colors"
          >
            kristenmartino.ai
          </Link>
          <Link
            href={site.repoUrl}
            target="_blank"
            rel="noreferrer"
            className="text-[var(--color-graphite-40)] hover:text-[var(--color-bone)] transition-colors"
          >
            github
          </Link>
        </div>
      </div>
    </footer>
  );
}
