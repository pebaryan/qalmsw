# Paper plan — small local LMs for scientific claim verification

## Research question

**How reliably can 7B–32B local (GGUF) LLMs verify that a cited abstract supports the
claim the authors attribute to it — and where does model scale, quantization, and prompt
structure break that reliability?**

This is the operating-point question a lab faces when choosing an on-prem model for
privacy-preserving manuscript QA. It is under-studied: frontier-model claim verification
has been explored (SciFact, FEVER-style tasks), but small-model behavior on
*scientific-writing-in-the-wild* claims has not. We operationalize "reliably" in two
complementary ways:

- **Accuracy on controlled synthetic defects** — known-label triples constructed by
  perturbing real paragraph-citation pairs. Measures whether the model gets the right
  answer when ground truth exists.
- **Judgment consistency** — self-agreement, cross-quantization, cross-family, and
  paraphrase-stability. Measures whether the model's verdicts are *stable enough to
  trust*, independent of whether any single verdict is "right".

## Contribution (what the paper sells)

1. **A synthetic-defect benchmark generator** that takes real arXiv paragraph-citation
   pairs and produces labeled `(paragraph, cite_key, abstract, label)` triples by
   controlled perturbation (abstract swaps, claim negation, abstract truncation). Labels
   are automatic. Released as a generator script, not a frozen dataset — reviewers and
   future work can regenerate at any scale, with any arXiv snapshot.
2. **Model-consistency diagnostics** that need no labels at all: self-agreement under
   resampling, cross-quantization agreement, cross-family agreement, and
   paraphrase-stability. Measures *reliability* — a judgment tool that flips verdicts
   between runs is broken regardless of which verdict is "right".
3. **A scale × quantization × prompt sweep** over local models (7B–32B) evaluated on
   both (1) and (2), plus a frontier baseline (three families via OpenRouter) as a
   ceiling.
4. **An operating-point recommendation** — "below X params / above Y quantization loss,
   contradiction recall on synthetic defects drops below Z%; practical local deployment
   should use ≥M."
5. **A VRAM-vs-accuracy plot** so readers can map "the card I have" → "the performance
   I should expect". Uncommon framing in NLP papers, directly actionable.
6. **Open tooling** — qalmsw as the evaluation harness, benchmark generator released
   under a permissive license.

## Scope discipline

Do **not** cover:
- Grammar / style QA (saturated literature; LanguageTool + Writefull already solve it).
- Reviewer-style critique (labels are too subjective for κ > 0.6).
- Retrieval reliability (Scholar scraping is an engineering problem, not a research one).
  Assume abstracts are given; the paper measures *judgment*, not retrieval.
- Multi-document / long-context reasoning. One paragraph, one abstract, one verdict.

## Benchmark design (synthetic-defect + consistency, human-light)

The methodology has two pillars. Neither requires panel labeling.

### Pillar 1 — Synthetic-defect benchmark

**Base corpus.** Sample ~500 `(paragraph, cite_key, abstract)` triples from arXiv
papers published 2024–2026 that list at least one `\cite{}` in a prose paragraph. For
each triple, the *base assumption* is label = `supports` — the authors' own
attribution, filtered to "accepted/published" venues to reduce the chance of a genuine
miscitation contaminating the base set. A small human spot-check (see Pillar 3) tests
this assumption.

**Defect operators** generate variants with automatic labels:

| Operator | Action | Ground-truth label |
|---|---|---|
| `swap-random` | Replace abstract with one from a randomly-sampled unrelated-field arXiv paper | `unrelated` |
| `swap-near` | Replace abstract with a same-field paper (embedding-nearest) that is not the original | `unrelated` (harder case — tests topicality vs. claim-specific support) |
| `truncate-head` | Keep only the first 1–2 sentences of the original abstract | `unclear` |
| `claim-negate` | Rewrite the paragraph's claim to its logical opposite (LLM-driven + pattern rules: "outperforms" ↔ "underperforms", "improves" ↔ "reduces", etc.), keep original abstract | `contradicts` |
| `claim-strengthen` | Upgrade a hedged claim to an absolute one ("often" → "always", "on some" → "on all") without changing the abstract | `unclear` or `contradicts` (ambiguous; validate by spot-check) |
| `identity` | No perturbation | `supports` (per base assumption) |

Each base triple seeds 1 `identity` and 2–3 defect variants, chosen per stratification
budget. Target: ~300 labeled triples total after generation, ~60 per class (skewed
slightly toward `supports` since identity is cheap and serves as the "true-positive"
reservoir).

**Claim-negation** is the trickiest operator. Use a frontier LLM (OpenRouter) at
temperature 0 with a rule-guided prompt to produce candidate negations, then gate each
candidate through an automatic filter: the negated claim must survive as a grammatical
sentence and diverge semantically from the original (measured by embedding distance
threshold). Rejections go back to the generator. This is *not* manual labeling — it's
an automated pipeline the paper describes and releases.

### Pillar 2 — Consistency diagnostics (label-free)

Measure judgment *reliability* independent of ground truth. For each model in the sweep:

- **Self-agreement.** Run N=5 samples at temperature 0.7 on every triple; report the
  fraction of triples where the modal verdict captures ≥4/5 samples.
- **Cross-quantization agreement.** Same family + param count, different quantization
  (Q4_K_M vs Q8_0 vs FP16): how often does the verdict flip?
- **Cross-family agreement.** Qwen-14B vs Llama-8B vs Gemma-9B at matched quantization:
  how often do they agree? Low agreement across families is a red flag *for the task
  itself*, not any one model.
- **Paraphrase-stability.** For a subset, feed a paraphrase of the paragraph (generated
  by a frontier model, deterministic temp=0); does the verdict survive?

These metrics are cheap, diagnostic, and label-free. They answer a question reviewers
actually care about: "is this judgment trustworthy enough to ship?"

### Pillar 3 — Human spot-check (small, bounded)

The base-assumption step (`identity` → `supports`) is a load-bearing claim. Validate
with a **single-rater review of 50 identity triples by the primary author**:

- If ≥90% are genuinely `supports`, the base assumption holds, full stop.
- If 80–90%, quantify contamination and discuss as a limitation.
- If <80%, the base corpus needs pre-filtering (e.g., higher-venue filter, or
  embedding-based claim-abstract similarity threshold).

This is ~4–6 hours of work, not 4 weeks. No panel, no κ calculation, no recruitment.

### Stratification

Sample the base corpus across:
- Claim type: methodological, empirical, definitional.
- Paper field (CS-ML / stats / biomedical — embedding-clustered; mixed fields stress
  cross-domain behavior).
- Abstract-paper relationship: self-cite, different-group, survey-citing-primary.

### Release

- Under CC-BY-SA (or similar). Release the **generator script + arXiv ID list + seed**,
  not the frozen triples — avoids copyright on abstracts/paragraphs, and makes the
  benchmark trivially regenerable at any scale.

## Sweep design

### Dimensions

| Axis | Values |
|---|---|
| Architecture family | Qwen2.5, Llama-3.1, Gemma-2, Mistral |
| Parameter count | 7B, 14B, 32B |
| Quantization | Q4_K_M, Q5_K_M, Q8_0, FP16 (where it fits) |
| Prompt | one-step judge; two-step extract-then-judge (qalmsw's default); chain-of-thought |
| Temperature | 0.0 (primary), 0.3 (sanity check for variance) |

Cap at **32B** — 70B is out because the ready fleet can't serve it without heavy CPU
offload, and "7B–32B is the practical local-deployment window" is a cleaner story.
Not every cross-product — a fractional factorial. Full sweep on one family (Qwen),
anchor points for the rest.

### Hardware fleet (confirmed)

| Host | GPUs | Role |
|---|---|---|
| A | V100 32GB (Volta) + Quadro P2000 (display only) | Workhorse for 14B Q8 and all 32B runs |
| B | RTX 5060 Ti 16GB (Blackwell) + RX 9060 XT 16GB (RDNA 4) | 5060 Ti = second primary CUDA pipeline; 9060 XT = AMD ablation via llama.cpp Vulkan backend |

Effective primary parallelism: **2** (V100, 5060 Ti). AMD 9060 XT contributes a
"same quant, different arch" ablation row, not primary results. Expect sweep
wall-time ≈ 2–3 days at realistic throughput.

**V100 / Volta caveat:** FP16-native, no BF16 tensor cores. Several modern checkpoints
ship BF16-first; silent downcast can shift accuracy 1–2 points. Policy: prefer
FP16-native GGUF weights where published, flag BF16-origin runs separately, and report
any V100-vs-5060-Ti delta on the same model as a data point (not a bug).

### Frontier baseline (via OpenRouter)

Three families, programmatic via OpenRouter's OpenAI-compatible API (qalmsw's existing
`LlamaCppClient` works with just a `base_url` + auth-header swap):

- **Anthropic**: `anthropic/claude-sonnet-4.6` or `claude-opus-4.7`
- **OpenAI**: `openai/gpt-5` (or `gpt-4o` if 5 is out of budget)
- **Google**: `google/gemini-2.5-pro`

Pin exact model snapshot IDs in the sweep config and paper appendix for
reproducibility. Budget estimate: ~300 triples × 2 calls × 3 models ≈ 1.8k calls at
~1.5k tokens avg → ~2.7M tokens → **$15–30** on OpenRouter.

Reported as a *ceiling*, not a direct competitor. Privacy, cost, and on-prem
deployment are axes the frontier doesn't compete on.

### Metric set

On the synthetic benchmark:
- **Primary:** macro-F1 across 4 labels vs. synthetic ground truth.
- **Critical:** contradiction recall. A tool that misses contradictions is worse than
  one that flags more false positives; weight this metric heavily in discussion.
- **Per-operator breakdown:** accuracy on `swap-random` vs `swap-near` vs `truncate-head`
  vs `claim-negate` — tells readers *which* failure modes each model handles.
- **Calibration:** reliability diagram on `supports` — when the model says "supports",
  how often is it right?

On consistency diagnostics:
- **Self-agreement rate** (modal verdict ≥4/5 at temp=0.7).
- **Cross-quantization flip rate** per model × per quant-pair.
- **Cross-family agreement matrix** at matched quantization.
- **Paraphrase-stability rate** on the subset.

Deployment-facing:
- **Cost & deployability:** tokens / second, latency per judgment, $ per 1k judgments
  (frontier) vs watts + VRAM (local).
- **VRAM-vs-accuracy plot:** x-axis = GGUF in-memory footprint, y-axis = contradiction
  recall (primary) and macro-F1 (secondary). Readers map their card → expected
  performance.

## Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Synthetic defects don't match natural miscitation failure modes | **High — central risk** | Explicit limitation; spot-check a sample of identity triples (Pillar 3); report per-operator results so readers see which defect types each model handles; future work promises naturalistic-miscitation extension |
| Base assumption (`identity` = `supports`) contaminated by real miscitations in the corpus | Medium | Spot-check 50 triples; filter by venue; report contamination rate |
| Claim-negation produces semantically vacuous sentences | Medium | Embedding-distance + grammaticality gate; manual review of negation operator on ~20 samples before full generation |
| Consistency metrics are low-information (everything agrees with itself trivially) | Low | Report the *disagreement* rates and the cross-family matrix — disagreement is the signal; also compare small-LM agreement to frontier-LM agreement as calibration |
| Local models refuse / loop on structured output | Low | qalmsw already handles lenient JSON parsing |
| Frontier baseline makes local models look pointless | Medium | Frame as *operating points*, not winners — privacy/cost are axes the benchmark doesn't measure |
| Reviewer pushback: "SciFact already exists" | High | Differentiate: SciFact is sentence-level, synthetic claims from wiki; ours is paragraph-level, cite-anchored, small-model-focused, and pairs accuracy with reliability diagnostics |
| Abstract-only is too little context | Medium | Report that limitation; optional ablation with full intro section as future work |

## Timeline (approximate, solo primary)

| Phase | Weeks |
|---|---|
| arXiv fetcher + base-corpus sampler + stratification | 1 |
| Defect-operator implementation (incl. negation pipeline) | 1–2 |
| Human spot-check of 50 identity triples | 0.5 |
| Sweep harness + model downloads | 1 (parallel w/ above) |
| Running the sweep (synthetic benchmark + consistency) | 1–2 |
| Frontier baseline runs (OpenRouter) | 0.5 |
| Analysis + writing | 2–3 |
| Buffer | 1 |
| **Total** | **~7–10 weeks** |

Compared to the original (12–14 weeks gated on a 3-person labeling panel), this is
roughly half the wall time and 100% of the work is doable solo.

## Target venues

**Primary candidates:**
- **SDP @ ACL/EMNLP** (Scholarly Document Processing workshop) — direct fit.
- **BioNLP @ ACL** — adjacent audience; accepts scientific-writing work.
- **NLP4Science** — newer, small-LM-friendly.

**Stretch:**
- EMNLP / NAACL Findings — if the operating-point result is striking (e.g., clear
  scale cliff).

**Preprint:**
- arXiv from week ~10, before workshop deadlines.

## What qalmsw already gives us

- Claim extraction + judge pipeline (`checkers/claims.py`).
- Bib + inline-bibliography parsing.
- Local llama.cpp client with JSON mode and lenient parse.
- Per-paragraph fan-out infrastructure.

## What's left to build

- **arXiv fetcher** — paper IDs → TeX source + metadata. (arXiv offers bulk source
  access; deterministic, no Scholar-style CAPTCHAs.)
- **Base-corpus sampler** — finds paragraphs with `\cite{}`, resolves cite keys against
  each paper's bib, fetches cited abstracts via arXiv API, applies stratification.
  Reuses qalmsw's paragraph/bib/citation parsers directly.
- **Defect operators** — one module per operator (`swap_random`, `swap_near`, `truncate`,
  `negate`, `strengthen`). Embedding-based similarity helpers shared.
- **Consistency harness** — N-sample runner at non-zero temperature, plus
  cross-model/cross-quant comparison aggregator.
- **Sweep runner** — `(model, quant, prompt) → benchmark run → metrics row`. Reuses
  qalmsw's claims pipeline; bypasses the CLI for parallel dispatch.
- **Analysis notebooks** — per-metric tables, VRAM-vs-accuracy plot, cross-family
  agreement matrix.

*Dropped from the previous plan:* labeling UI, annotation CSV workflow.

## Resolved constraints (2026-04-22)

- **Hardware:** 2 hosts — V100 32GB + 5060 Ti 16GB primary CUDA; 9060 XT 16GB for AMD
  ablation. Sweep capped at 32B.
- **Frontier baseline:** OpenRouter API (credits already available). Three-family
  lineup above. Budget ~$15–30 of credits.
- **Methodology:** synthetic-defect + consistency-diagnostics, single-rater spot-check
  only. No panel labeling.

## Open questions for the user

1. Field breadth of the base corpus: stay in CS/ML (simpler), or stratify across CS +
   stats + biomedical for a cross-domain story?
2. Negation operator — is LLM-assisted generation acceptable (cheap, OpenRouter-driven,
   but introduces frontier-LLM dependency into benchmark construction), or should we
   restrict to rule-based templates (purely deterministic, narrower claim coverage)?
3. Should `claim-strengthen` stay in the operator set despite its ambiguous label, or
   drop it and rely on the four cleaner operators?
