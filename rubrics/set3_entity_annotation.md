# Set 3 — Entity Annotation Rubric

**Status:** Draft v0.2 — major decisions resolved; remaining Sift-specific TODOs at the bottom.
**Scope:** n=100 articles, manual annotation per spec §2 Task C and §4 Set 3.
**Prerequisite:** 10 calibration articles dual-annotated by two annotators with IAA ≥0.85 before annotating items 1–100.

---

## Goal

For each article, produce a structured JSON record of:
1. **Named entities** — people, organizations, locations — with character offsets.
2. **Key claims** — verbatim spans of factual statements germane to the article's topic.

This rubric is the authority on annotation decisions. When an article is ambiguous: refer here, then to the calibration set, then escalate.

---

## Entity types

### PERSON
Real, named individuals.
- **Include:** "Dr. Jane Smith", "President Lula da Silva", "Elon Musk"
- **Include:** named individuals even when referenced by title later — annotate the named span only, not pronouns or generic titles
- **Exclude:** generic references — "the CEO", "a researcher", "doctors"
- **Exclude:** fictional characters unless the article is about them (e.g., a film review naming the character)

### ORG
Organizations: companies, government bodies, NGOs, universities, sports teams.
- **Include:** "Anthropic", "Department of Energy", "MIT", "United Nations"
- **Include:** news outlets when explicitly cited as a source ("according to Reuters")
- **Include parent companies** when product names appear: "Apple announced the iPhone 16" → annotate `Apple` (ORG); skip `iPhone 16` (product, not org).
- **Include financial entities as the underlying company, not the ticker or instrument:**
  - `$TSLA reached $300` → annotate `$TSLA` (ORG, refers to Tesla).
  - `S&P 500 closed up 1%` → don't annotate (benchmark, not an organization).
  - For ETFs, annotate the issuer, not the fund: `Vanguard Total Stock` → annotate `Vanguard` only.
- **Exclude:** industries or sectors — "the tech industry", "energy sector"
- **Exclude:** generic groups — "the government", "researchers" without an institutional name
- **Exclude product names** that aren't org references: "iPhone sales fell" → annotate nothing (no org named).
- **Edge case:** Subsidiary/parent — annotate the most specific entity named ("Google DeepMind", not "Google", if both appear in the same sentence as distinct references)

### LOC
Locations: countries, states, cities, regions, named landmarks.
- **Include:** "Florida", "São Paulo", "the Sahara", "Times Square"
- **Include:** facilities with proper names — "Three Mile Island", "Cape Canaveral"
- **Exclude:** generic locations — "downtown", "the office" — unless named
- **Exclude:** street addresses unless they identify a notable landmark

---

## Span boundary rules

- Annotate the **shortest contiguous span** that captures the entity name.
- **Include** titles when fused with the name: "President Biden" → one PERSON span.
- **Exclude** qualifying phrases that change reference: "former CEO Sundar Pichai" → span covers "Sundar Pichai" only.
- **Exclude** punctuation that's not part of the name (commas, periods, parentheses).
- **Tie-breaker:** when in doubt, prefer the shorter span.

---

## Inclusion criteria

Annotate every distinct entity *each time it appears as a named span* (do not resolve coreference). If "Apple" appears 5 times, annotate 5 spans with the same entity.

**Skip:**
- Entities mentioned only inside direct quotes that aren't germane to the article's main topic.
- Boilerplate or syndicated content (AP wire byline, "© 2024 Reuters", republishing notices).

---

## Key claims

For each article, extract up to **10 key claims**. A "key claim" is:
- A factual statement germane to the article's main topic.
- Stated as a declarative sentence (not a question, not a quote unless the speaker is the source of the fact).
- Verifiable from the article body alone — not external knowledge.

**Format:** verbatim span from the article body, with character offsets. If the original sentence is too long (>40 words), select the smallest contiguous sub-span that preserves the claim.

**Edge case:** causal claims ("X caused Y") count if they're explicit in the text. Do not infer.

---

## Disambiguation guide

When an entity could fit multiple types:
- **"Microsoft"** describing the building → ORG (the company is the canonical referent)
- **"Washington"** the city vs. the state vs. George Washington → use surrounding context; if ambiguous, prefer the most prominent referent in the article
- **Sports team named after a city** (e.g., "the Yankees") → ORG
- **A landmark named after a person** (e.g., "the Lincoln Memorial") → LOC

---

## Calibration protocol

Before annotating items 1–100, dual-annotate **10 calibration articles** with a second annotator. The second annotator should have basic technical literacy and ~1 hour of time. This is **real inter-annotator agreement (IAA)**, not solo intra-annotator consistency.

Calibration articles are **drawn from outside Set 1's eval pool** — don't burn eval items on calibration. Recommend stratified across categories from §4 Set 1, with at least one short and one long article in the calibration set.

Compute IAA:
- **Entity F1** across the calibration set
- **Target:** ≥ 0.85 IAA

If IAA is below target:
1. Surface every disagreement
2. Refine this rubric (the disagreement points to ambiguity)
3. Re-annotate the calibration set
4. Repeat until ≥ 0.85

Document the final IAA score in the methodology page.

**Fallback if second annotator becomes unavailable:** solo dual-annotate with a 24-hour gap, and rename the metric in the methodology page from "IAA" to "intra-annotator consistency." Be explicit about the change — the difference matters for credibility.

---

## Tooling

JSONL + VS Code. Pair with a `validate_annotations.py` script that:
- Validates each row against the schema
- Counts entities by type per article
- Flags suspicious cases (zero entities in long articles, single-character spans, etc.)
- Reports cross-article stats for spot-checking

---

## Output format (per article)

```json
{
  "article_id": "<sift_id>",
  "annotator": "<initials>",
  "annotated_at": "<ISO timestamp>",
  "entities": [
    {"type": "PERSON", "span": "Jane Smith", "start": 142, "end": 152},
    {"type": "ORG",    "span": "Anthropic",  "start": 201, "end": 210}
  ],
  "claims": [
    {"text": "Verbatim claim from article body.", "start": 489, "end": 533}
  ]
}
```

---

## Sift-specific TODOs (Kristen to fill in before kickoff)

- [ ] Confirm Sift's article corpus is English-only. Non-English content needs separate rules.
- [x] **Brand names:** annotate parent company only — "Apple" yes, "iPhone" no. (Decided 2026-05-06.)
- [x] **Financial instruments:** annotate underlying company entity (e.g., "$TSLA" for Tesla); skip benchmarks (e.g., "S&P 500"); for ETFs annotate the issuer. (Decided 2026-05-06.)
- [ ] **Decide:** Should hashtags or @mentions be annotated if articles include social-media-style content? Currently EXCLUDED.
- [x] **Calibration:** 10 articles, dual-annotated with second annotator, drawn from outside Set 1 pool. (Decided 2026-05-06.)
- [x] **Tooling:** JSONL + VS Code + `validate_annotations.py`. (Decided 2026-05-06.)
- [ ] Confirm article ID format and how character offsets relate to the article body field stored in Sift.
- [ ] Identify the second annotator and confirm their ~1 hour availability.
