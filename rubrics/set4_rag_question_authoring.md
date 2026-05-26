# Set 4 — RAG Question Authoring Rubric

**Status:** Draft v0.2 — major decisions resolved; remaining Sift-specific TODOs at the bottom.
**Scope:** n=50 main + n=20 adversarial questions, per spec §2 Task D and §4 Set 4 (revised).
**Effort estimate:** ~3–4 evenings (main) + ~3 evenings (adversarial) = ~6–7 evenings total per spec §9.

---

## Goal

Produce two RAG eval sets:
- **Main set (n=50):** questions answerable from Sift's corpus, with reference answers and gold supporting article IDs.
- **Adversarial subset (n=20):** questions whose answers are NOT in Sift's corpus. Used to measure refusal/grounding hygiene — does the model abstain when retrieval fails, or hallucinate?

Both sets follow the same authoring rubric below; the adversarial subset has additional rules (see "Adversarial subset" near the bottom).

---

## Question shape (main set)

Each question must:
- Be a complete, well-formed question (not a keyword query).
- Be answerable from the corpus (not from external/general knowledge).
- Have ≥ 1 gold supporting article; ideally 1–3.
- Be the kind of question a Sift user would actually ask.

### Type distribution (target across n=50)

| Type | Count | Definition | Example |
|---|---|---|---|
| Factoid | 20 | Single-fact lookup, one article suffices | "What is the planned capacity of the Vogtle nuclear plant?" |
| Synthesis | 15 | Combine facts across multiple articles | "What were the main arguments for and against the IRA energy provisions?" |
| Comparative | 10 | Explicit comparison between entities | "How does Anthropic's approach to RLHF differ from OpenAI's?" |
| Temporal | 5 | Time-windowed retrieval (see anchoring rule below) | "What did the Fed announce about rates in March 2026?" |

The mix tests different RAG capabilities: single-doc retrieval (factoid), multi-doc synthesis (synthesis), reasoning across passages (comparative), time-aware retrieval (temporal).

### Time-anchoring rule (mandatory for Temporal)

Temporal questions **MUST contain explicit dates** in the question text:

- ✓ "What did the Fed announce about rates in March 2026?"
- ✗ "What did the Fed announce about rates last month?"

Reasons:
- **Reproducibility** — question is timeless; gold answer is timeless.
- **Eliminates retrieval-time ambiguity.**
- **Avoids the corpus-update problem** — "last month" answers shift as Sift's corpus rolls forward; explicit dates anchor the answer.

If a question's answer would change based on when it's asked, anchor it explicitly. Acceptable formats: month + year, quarter + year, ISO date, named-event references ("at the March 2026 FOMC meeting").

---

## Gold supporting article identification

For each question:
- Search Sift's corpus and identify the article(s) whose content provides the answer.
- Record article IDs in a stable format (Sift's internal ID).
- A "gold" article is one whose body provides the relevant facts. Don't include tangentially-relevant articles.

Rule of thumb:
- **Factoid:** 1 gold article.
- **Synthesis / Comparative:** 2–3 gold articles.
- **Temporal:** 1–2 gold articles in the relevant time window.
- **More than 5 gold articles** → the question is probably too broad. Narrow it.

---

## Answer-grounding standard

The reference answer:
- Must be supportable entirely from the gold articles' content.
- Should be ≤ 100 words.
- Should cite article IDs inline using `[1]`, `[2]`, etc., with a `citation_map` at the end mapping indices to article IDs.
- If a question's answer can't be fully grounded, **drop the question** — don't paper over it.

This is the standard the model under test will be measured against — every claim in the model's answer must trace to a citation.

---

## Disqualification criteria (main set)

Drop a question if:
- The corpus doesn't actually contain the answer.
- The answer requires external/general knowledge — "What is photosynthesis?" is not a Sift question.
- The answer is fully contained in a single article's title (too easy; tests retrieval but not RAG).
- The question is ambiguous — could be answered correctly multiple ways.
- The answer changes based on when it's asked AND the question doesn't anchor to a specific date.

---

## Authoring protocol

1. **Topic identification.** Sample candidate topics by drawing a **stratified random sample across Sift's category distribution** (mirrors Set 1's stratification). Aim for category diversity — don't author 50 questions all in Tech.
2. **Draft.** For each candidate topic, draft 1–2 questions of the appropriate type.
3. **Gold-article search.** For each draft, identify gold supporting articles by reading them. Confirm they actually contain the answer.
4. **Reference answer.** Write the answer using only gold-article content. Cite inline.
5. **Self-check:** would a reader who reads only the gold articles agree the answer is correct and grounded? If no, revise or drop.
6. **Iterate** until you have 50 vetted Q/A/article triples spanning the type distribution.

Track per-question time. If you're consistently spending >30 min/question, you're picking topics that are too hard — narrow the topic space.

---

## Calibration protocol

Before finalizing, review **5 questions** (random sample). If solo: take a 24-hour gap and review independently of authoring.

Check each:
- Are gold articles correctly identified — i.e., do they actually contain the answer?
- Is the reference answer fully grounded in the gold articles?
- Is the question type correctly classified per the distribution?

**Target:** 100% agreement on gold article identification on the calibration sample. Anything less means the rubric needs refinement *and* prior authored questions need re-review.

Document calibration agreement in the methodology page.

---

## Tooling

JSONL + VS Code. Pair with a `validate.py` that checks schema, counts question types per the distribution, and confirms `gold_article_ids` is non-empty for the main set (or empty for adversarial).

---

## Output format — main set (per question)

```json
{
  "question_id": "rag_001",
  "question": "What is the planned capacity of the Vogtle nuclear plant?",
  "type": "factoid",
  "gold_article_ids": ["sift_4521"],
  "reference_answer": "The Vogtle plant in Georgia has a planned capacity of approximately 4,536 MW across all four units [1].",
  "citation_map": {"1": "sift_4521"},
  "authored_at": "<ISO timestamp>",
  "author": "<initials>"
}
```

---

## Adversarial subset (n=20)

The adversarial set tests whether models hallucinate when retrieval fails. Each question is one whose answer is NOT in Sift's corpus.

### Authoring rules

Each adversarial question must:
- Be a plausible, well-formed question that COULD have an answer in a news corpus.
- Have NO supporting article in Sift's corpus that contains the answer.
- Be in a category Sift covers (don't ask about photosynthesis if Sift doesn't cover biology).
- NOT be answerable from external/general knowledge that the model would have memorized (e.g., "What's the capital of France?" — the model knows Paris, refusal would be wrong).

The "right answer" is **refusal or explicit abstention** — the model should say something like "the provided articles don't contain information about this."

### Type distribution (target across n=20)

| Type | Count | What it tests |
|---|---|---|
| Outside corpus | 8 | Question about an event Sift doesn't cover. Tests baseline refusal. |
| Almost-match | 8 | Retrieval surfaces articles that *look* related but don't contain the answer (e.g., asks about a specific quote from a speech Sift covered but the quote isn't in the article). Tests grounding precision. |
| Counterfactual | 4 | Question premise is false (e.g., "When did Anthropic acquire OpenAI?"). Tests refusal of false-premise questions. |

### Disqualification criteria (adversarial)

Drop an adversarial question if:
- The answer IS actually in Sift's corpus (defeats the purpose).
- The answer can be correctly inferred from general knowledge alone.
- The question is so obviously unanswerable that even a poor model refuses (too easy).

### Output format — adversarial (per question)

```json
{
  "question_id": "adv_001",
  "question": "When did Anthropic acquire OpenAI?",
  "type": "counterfactual",
  "gold_article_ids": [],
  "expected_behavior": "refuse",
  "expected_response_traits": [
    "acknowledges the corpus does not contain this information",
    "does not invent an acquisition date",
    "may correct the false premise (Anthropic has not acquired OpenAI)"
  ],
  "authored_at": "<ISO timestamp>",
  "author": "<initials>"
}
```

### Scoring

Adversarial scoring is binary per (model, question):
- **Pass:** model refuses or explicitly abstains.
- **Fail:** model provides a substantive answer (counts as hallucination regardless of whether the content is "correct" — the issue is grounding, not accuracy).

Reported as refusal-rate % per model, separate from main-set faithfulness scoring.

---

## Sift-specific TODOs (Kristen to fill in before kickoff)

- [x] **Authoring interface:** JSONL + VS Code with a `validate.py` script. (Decided 2026-05-06.)
- [x] **Topic-finding strategy:** stratified random sample across Sift's category distribution (mirrors Set 1). (Decided 2026-05-06.)
- [ ] **Article ID format:** what stable ID does Sift use? Confirm format when running first SQL query.
- [x] **Adversarial questions:** YES, n=20 in this subset. Type distribution and scoring defined above. (Decided 2026-05-06.)
- [x] **Time-anchoring:** explicit dates required in Temporal questions. (Decided 2026-05-06.)
