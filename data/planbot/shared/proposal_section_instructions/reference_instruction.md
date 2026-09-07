# References
```yaml
instructions: |
  Output a references section listing the source materials that were used to
  build this proposal, grouped by category. Use only materials that were
  actually provided in the reference JSON — do not invent citations.

  Include only the categories you actually used:
  - Client Profile: client demographics, profile, and holdings.  Provided via
    the `api://client_profile` reference.
  - Product Catalog: investable products, holdings, alternatives, and fitness
    scores.  Provided via the `api://product_catalog` reference — there are no
    static product-catalog files in the prompt.
  - Market Outlook: market outlook and sentiment documents.
  - Proposal Guidelines: the proposal and section instruction documents.
  - Web References: external URLs from the shared `web_references` section
    (`websites.md`), or "N/A" if none were used.

  When citing API-backed materials, use the `api://` path as the reference
  name (e.g. `api://product_catalog`).  Do not cite static files that were not
  provided in the reference JSON.

  Output the section under a "# References" heading (level-1, or level-2 to
  match the proposal's existing heading hierarchy).
```

Example (ILLUSTRATIVE ONLY — the file names below are fake placeholders; list
only the materials actually provided in your reference JSON, never these):

- Client Profile: api://client_profile (Planbot Internal Data)
- Product Catalog: api://product_catalog (Planbot Internal Data)
- Market Outlook: <example_market_outlook_1.md>, <example_market_outlook_2.md> (Planbot Internal Data)
- Proposal Guidelines: <example_proposal_format.md>, <example_section_instruction.md> (Planbot Internal Data)
- Web References: N/A (data sourced from internal repositories)
