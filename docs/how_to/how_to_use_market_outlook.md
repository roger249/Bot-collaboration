# How to Use the `market_outlook` Parameter

This document shows an **external caller** how to pass a market outlook into the
proposal APIs. It is written for LLM/coding consumption: field names, JSON
shapes, and worked examples are exact.

The same mechanism applies to **all** proposal endpoints. This guide uses
`POST /api/v1/product-investor-matcher` as the running example; the identical
`market_outlook` field exists on the other endpoints (`reinvestment-proposals`,
`propose_reinvestment_for_maturing_holdings`, `product-opportunity-proposal`,
`product-opportunity-proposal-automatch`, `portfolio-review`,
`llm-product-matcher`).

---

## 1. The field

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `market_outlook` | string | no | Free-form market narrative (Markdown) injected into the LLM context. |

When `market_outlook` is null or empty, the server falls back to the bundled
static reports — the caller does not need to supply it.

---

## 2. The source files

The bundled market outlook lives in `data/planbot/shared/market_outlook/`. It
consists of four Markdown files that the caller may read, concatenate, and pass
in as a single `market_outlook` string:

| File | Title | What it provides | Typical use |
| --- | --- | --- | --- |
| `bea_wise.md` | BEA Wise Q3 2026 Market Outlook Summary | Macro theme, regional macro analysis, asset-class strategies & targets | Broad top-down context |
| `bea_research_1.md` | BEA FundWatch 投資卓見 (Issue 3) | Fund performance tables across bonds, multi-asset, equity, sector | Fund selection context |
| `bea_research_2.md` | BEA 投資產品及顧問部 — HALO strategy | HALO (Heavy Assets, Low Obsolescence) infra strategy | Defensive / infra tilts |
| `bea_research_3.md` | BEA Economic Indicators Analysis | HK external-trade / export momentum | Macro data point |

---

## 3. How to pass the four files as one string

Read the four files, join them with `\n\n`, and put the result in
`market_outlook`.

### 3.1 Build the concatenated string (conceptual)

```
combined = read("bea_wise.md")
         + "\n\n"
         + read("bea_research_1.md")
         + "\n\n"
         + read("bea_research_2.md")
         + "\n\n"
         + read("bea_research_3.md")
```

The resulting `combined` value is a single Markdown string: the four reports
appended in order, separated by blank lines.

### 3.2 Python example

```python
from pathlib import Path

outlook_dir = Path("data/planbot/shared/market_outlook")
files = ["bea_wise.md", "bea_research_1.md", "bea_research_2.md", "bea_research_3.md"]

market_outlook = "\n\n".join(
    (outlook_dir / f).read_text(encoding="utf-8").strip() for f in files
)

payload = {
    "product_source": "default_yaml",
    "product_ids": ["bank_recommended"],
    "client_selection": {"client_id": ["PB-HK-000001-8"]},
    "market_outlook": market_outlook,
}
```

### 3.3 cURL example (single file content inlined)

```bash
curl -X POST http://localhost:8000/api/v1/product-investor-matcher \
  -H "Content-Type: application/json" \
  -d '{
    "product_source": "default_yaml",
    "product_ids": ["bank_recommended"],
    "client_selection": {"client_id": ["PB-HK-000001-8"]},
    "market_outlook": "# BEA Wise Q3 2026 Market Outlook Summary\n\n## Executive Overview & Macro Theme\n\n…(full file content here)…\n\n# BEA 東亞銀行 — FundWatch 投資卓見\n\n…(full file content here)…"
  }'
```

For a real multi-file call, build the string in code (§3.2) rather than
hand-inlining in cURL.

---

## 4. Notes for the caller

- **`market_outlook` is free-form Markdown.** Any narrative is accepted — it does
  not have to come from the four bundled files.
- **Empty/omitted → server fallback.** If `market_outlook` is `null` or `""`, the
  server uses its own static default; supplying a value overrides it.
- **The parameter name is `market_outlook`.** Internally the pipeline maps it to
  the `request.market_outlook_text` key — callers never see this; only the
  external `market_outlook` field matters.
- **Join separator.** Separate the reports with a blank line (`\n\n`) so the LLM
  sees clean section boundaries between the four reports.