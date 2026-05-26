import type { MDXComponents } from "mdx/types";

const components: MDXComponents = {
  h1: ({ children }) => (
    <h1
      className="font-semibold text-[var(--color-bone)] mt-16 mb-6"
      style={{
        fontSize: "var(--text-h1)",
        letterSpacing: "var(--tracking-display)",
        lineHeight: "var(--leading-tight)",
      }}
    >
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2
      className="font-semibold text-[var(--color-bone)] mt-14 mb-5"
      style={{
        fontSize: "var(--text-h3)",
        letterSpacing: "var(--tracking-tight)",
        lineHeight: "var(--leading-tight)",
      }}
    >
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3
      className="font-semibold text-[var(--color-bone)] mt-10 mb-4"
      style={{
        fontSize: "var(--text-h4)",
        letterSpacing: "var(--tracking-tight)",
      }}
    >
      {children}
    </h3>
  ),
  p: ({ children }) => (
    <p className="mb-5 text-base md:text-lg leading-relaxed text-[var(--color-graphite-20)] max-w-3xl">
      {children}
    </p>
  ),
  ul: ({ children }) => (
    <ul className="mb-6 ml-6 list-disc space-y-2 text-base md:text-lg leading-relaxed text-[var(--color-graphite-20)] max-w-3xl marker:text-[var(--color-graphite-60)]">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-6 ml-6 list-decimal space-y-2 text-base md:text-lg leading-relaxed text-[var(--color-graphite-20)] max-w-3xl marker:text-[var(--color-graphite-60)]">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="pl-1">{children}</li>,
  a: ({ href, children }) => (
    <a
      href={href}
      className="text-[var(--color-signal-blue-soft)] underline underline-offset-4 decoration-[var(--color-graphite-80)] hover:decoration-[var(--color-signal-blue)] transition-colors"
      target={href?.startsWith("http") ? "_blank" : undefined}
      rel={href?.startsWith("http") ? "noreferrer" : undefined}
    >
      {children}
    </a>
  ),
  strong: ({ children }) => (
    <strong className="text-[var(--color-bone)] font-semibold">
      {children}
    </strong>
  ),
  em: ({ children }) => (
    <em className="italic text-[var(--color-bone)]">{children}</em>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-10 pl-6 border-l-2 border-[var(--color-signal-blue)] font-mono text-base md:text-lg leading-snug text-[var(--color-bone)] max-w-2xl">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-12 border-t border-[var(--color-graphite-90)]" />,
  code: ({ children }) => (
    <code className="font-mono text-sm bg-[var(--color-graphite-90)] text-[var(--color-bone)] px-1.5 py-0.5 rounded-sm">
      {children}
    </code>
  ),
};

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <article className="mx-auto max-w-6xl px-6 md:px-10 py-16 md:py-24 prose-mdx">
    {children}
  </article>
);

export function useMDXComponents(): MDXComponents {
  return { ...components, wrapper };
}
