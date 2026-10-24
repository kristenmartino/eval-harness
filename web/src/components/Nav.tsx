import Link from "next/link";
import { site } from "@/content/site";

const navItems = [
  { href: "/methodology", label: "Methodology" },
  { href: "/leaderboard", label: "Results status" },
  { href: "/executive-summary", label: "Summary" },
  { href: site.repoUrl, label: "GitHub", external: true },
];

export function Nav() {
  return (
    <nav className="sticky top-0 z-50 w-full border-b border-[var(--color-graphite-90)] bg-[var(--color-soot)]/85 backdrop-blur-md">
      <div className="mx-auto max-w-6xl px-6 md:px-10 py-4 md:py-0 md:h-14 flex flex-col md:flex-row items-start md:items-center gap-3 md:gap-0 md:justify-between">
        <Link
          href="/"
          className="shrink-0 whitespace-nowrap font-mono text-[var(--text-meta)] tracking-[var(--tracking-mono-tight)] uppercase text-[var(--color-bone)] hover:text-[var(--color-signal-blue-soft)] transition-colors"
        >
          eval-harness
        </Link>
        <ul className="flex flex-wrap items-center gap-x-4 gap-y-2 md:gap-8">
          {navItems.map((item) => (
            <li key={item.href}>
              <Link
                href={item.href}
                target={item.external ? "_blank" : undefined}
                rel={item.external ? "noreferrer" : undefined}
                className="font-mono text-[var(--text-meta)] tracking-[var(--tracking-mono-tight)] uppercase text-[var(--color-graphite-40)] hover:text-[var(--color-bone)] transition-colors"
              >
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}
