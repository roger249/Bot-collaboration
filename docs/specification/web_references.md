# Web References — Shared Preferred & Blocked Website Lists

> Status: **Draft** (all open issues resolved; see §8)

## 1. Objective

Centralize the list of external websites the LLM is allowed/encouraged to visit
into a single shared location, rather than scattering ad-hoc links inside
proposal-specific folders. Two lists are maintained:

1. **Preferred websites** — sites the LLM *should* consult (an allow-list of
   trusted sources).
2. **Blocked domains** — domains the LLM *must not* access (a deny-list).

Both are injected into the reference payload for the web-capable proposals, so
the LLM can honour them when using web-retrieval tools.

## 2. Scope

Applied to the **two proposals that declare web tools** (stock_analysis is
removed from scope for now):

| Proposal | Config shape | Web tools |
| --- | --- | --- |
| `llm_product_matcher` | `pipeline.<id>` | `SerpApiGoogleSearchTool`, `ScrapeWebsiteTool` |
| `portfolio_review` | `pipeline.<id>` | `SerpApiGoogleSearchTool`, `ScrapeWebsiteTool` |

The remaining proposals (`product_investor_matching`, `reinvestment`,
`product_opportunity`, `product_opportunity_automatch`) declare **no web tools**
and are out of scope. `stock_analysis` is also out of scope for now (it uses the
legacy top-level config shape and will be handled separately later).

## 3. File layout

```
data/planbot/shared/web_references/
    websites.md            # allow-list (preferred) of trusted URLs/domains
    blocked_domains.md     # deny-list of domains to avoid
```

Both are Markdown reference documents (not code), so the LLM reads them as
guidance. Each file states its purpose in a heading and lists one entry per
line. The allow-list is named `websites.md` (not `preferred_websites.md`) so the
existing `extract_urls_from_references` helper — which keys on that filename —
populates the `urls` list for free.

### 3.1 `websites.md` (indicative)

```markdown
# Websites

Prefer these sources when researching market/product context. Prefer them over
unknown search results of similar relevance.

- https://www.hkbea.com/...    # BEA best-selling unit trusts
- https://www.hsbc.com.hk/...  # HSBC MPF scheme brochure
- ...
```

### 3.2 `blocked_domains.md` (indicative)

```markdown
# Blocked Domains

Do not access these domains under any circumstances.

- example.com
- ...
```

## 4. Config wiring

Add a `web_references` reference input to each of the two in-scope proposals.

Add under each `pipeline.<id>.inputs`:

```yaml
- id: web_references
  source: file
  paths:
    - data/planbot/shared/web_references/*.md
  prompt_section: references
  required: false
```

Add a shared purpose under `input_defaults.by_id` so the section is
self-describing (mirrors `financial_needs_guidelines` etc.):

```yaml
input_defaults:
  by_id:
    web_references:
      description: Preferred websites and blocked domains for web retrieval
```

### 4.1 Dedicated URL injection (agreed)

The allow-list (`websites.md`) URLs are additionally exposed to the LLM as a
**dedicated, structured `urls` list** in the reference payload, so the model can
scrape them immediately without re-parsing markdown prose.

> **Current state:** the `urls` list is computed in `run_crew_planbot` but used
> only for the `urls_used` observability count — it is **not** injected into the
> prompt today. This is therefore a small code change.

Change: in `src/planbot/crew_workflow.py`, after computing `urls`, pass it into
`_build_reference_payload` (or `_build_user_prompt`) so the payload gains a
`"urls": [...]` field alongside `"sections"` (and `schema_version`). The
`websites.md` reference section remains for human/LLM readability; the `urls`
field is the machine-scrape-ready list.

## 5. Enforcement semantics (resolved) (resolved)

**Prompt-level (soft) only.** The LLM reads the lists as reference and is
instructed to comply; it treats the blocked list as a **soft criterion** and
decides for itself. **No code-level (hard) enforcement** (tool wrappers refusing
blocked domains) for now.

## 6. Migration / cleanup

1. Create `data/planbot/shared/web_references/websites.md` and
   `blocked_domains.md`.
2. **Fold in** the single link from
   `data/planbot/portfolio_review/proposal_instructions/website references.md`
   (BEA best-selling unit trusts) into `websites.md`, then **delete**
   `website references.md`.
3. Add the `web_references` input to the two in-scope proposals (§4) and the
   dedicated `urls` injection (§4.1).
4. Update `reference_instruction.md` (resolved decision 4).

## 7. Related machinery (context)

- `src/planbot/crew_workflow.py` computes `urls = cfg.urls + extract_urls_from_references(...)`
  but only uses it for the `urls_used` observability count — it is **not**
  injected into the prompt (to be fixed per §4.1). `extract_urls_from_references`
  keys on a file named `websites.md`, which aligns with the chosen filename.
- `src/planbot/config.py` `PlanBotConfig.urls` / `web_access` are legacy fields
  not currently exercised by the pipeline path.
- `data/planbot/shared/no_external_web_note.md` already exists as a fallback
  note when web access fails (see resolved issue 5).
- `data/planbot/stock_analysis/crewai/tasks.yaml` still references
  `news_and_data/preferred_websites.md` and `news_and_data/blocked_domains.md`
  (neither file exists). This is a pre-existing dangling pointer that is **out
  of scope** here but worth a follow-up.

## 8. Resolved decisions (review 2026-09-03)

| # | Decision |
| --- | --- |
| 1 | **Soft-only enforcement.** The LLM decides as a soft criterion; no code-level blocking of blocked domains. |
| 2 | **Allow-list named `websites.md`** (aligns with `extract_urls_from_references`). |
| 3 | **Dedicated `urls` list injected** into the reference payload so the LLM can scrape immediately (§4.1). |
| 4 | **Update `reference_instruction.md`** — its "Web References" bullet points at the shared `web_references` section (was: the deleted "website references" document). |
| 5 | **`blocked_domains.md` and `no_external_web_note.md` are distinct and complementary** — see below. |

### 8.1 Issue 5 — "must not access" vs. "cannot access" (resolved)

Confirmed: the two are different concepts and coexist without conflict.

| File | Concept | When it applies |
| --- | --- | --- |
| `blocked_domains.md` | **Policy deny-list** — the LLM *must not* access these domains. | Always (a constraint the LLM honours). |
| `no_external_web_note.md` | **Capability fallback** — the LLM *cannot* reach external sites (technical failure / no tool access), so it must state URL-based evidence is unverified. | Only when web access is unavailable or fails. |

`blocked_domains.md` is injected as part of `web_references`; `no_external_web_note.md`
remains the standalone contingency note already wired via `shared_no_web_note_file`.
No change to `no_external_web_note.md` is required.
