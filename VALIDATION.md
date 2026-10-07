# Validation and preparation notes

The complete notebook was executed from all five supplied traffic archives and the official BTS aircraft lookup in a fresh Python 3.12 process. All 15 code cells completed; saved outputs include tables and three figures. The portable runner executes the same cells through IPython without needing a Jupyter server. Interactive Jupyter launching was not tested in this environment because local sockets were unavailable.

## Comparison with the original analysis

- Market model: 7,599 monthly observations, 45 routes, 20 carriers.
- In-sample weighted R²: 0.6581624 for the market model and 0.7891793 after adding carrier indicators.
- Annual traffic totals, model sample counts, and aircraft quality counts match the original results. Differences in other floating-point fit metrics are below 10⁻¹².
- Retained corrections: 120 SQ A380-coded rows analyzed as 777-300ER and 88 SQ/OZ A350-coded rows analyzed as A380.
- Remaining quality decisions: 14 freighter rows removed, 600 reviewed low-density configuration rows retained, 394 unresolved rows excluded from the model, three carrier-years with mechanical freight flagged.
- Taiwan inbound/outbound flight totals reconcile in all four years.

## Checks performed

Three targeted tests pass: aircraft correction scope preserves original fields and leaves unrelated carriers unchanged; the weighted model uses departures; annual gauge/residual aggregation uses capacity totals rather than an unweighted average. Input checks require complete years and matching aircraft descriptions in the analytical market. All three figures were visually reviewed.

## Repository changes

The notebook now delegates source parsing, quality rules, and model helpers to `src/`. It uses project-relative paths and an explicit dependency file. No packages install automatically from notebook cells. The duplicate focus-case figure is removed. Fit metrics are explicitly labeled in-sample, and selected Japan routes are described as illustrative rather than the two largest contrasts.

A new common-sample freight table directly supports the focus-case discussion. Adding freight changes the ANA/United LAX–HND residuals from −42.31/+60.01 to −40.89/+57.59 seats, and JAL/United SFO–NRT from −64.32/+51.63 to −62.79/+51.49. These remain descriptive residuals.

Carrier-specific aircraft inferences retain the author's manual review and original reported fields; correction logs are exported. Raw archives are excluded from the repository. Input SHA-256 digests and package versions are in `results/`.

The original uploaded notebook and output archive were not modified. No forecasting accuracy, causal demand effect, profit estimate, or optimal aircraft assignment is claimed.
