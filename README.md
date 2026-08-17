# NYC Building Stories

A data visualization project exploring NYC's **Open HPD Violations** dataset (`csn4-vhvf`) to understand what public housing-violation records reveal about individual buildings and NYC's housing stock as a whole.

This is a data-exploration and storytelling project, not a decision-support product. It stops at **evidence → pattern → story**. It does not make recommendations or tell anyone what to do — that's a separate, later project.

## The question

> **What is happening to NYC's buildings, and what patterns are visible in the city's housing violation records?**

## The user

> Anyone trying to understand NYC housing conditions through public data — no recommendation, no decision engine, just an honest, evidence-backed exploration of what the data shows.

## The insight we're after

Not "this building has 42 violations." We're after transformations like recurrence, persistence, severity, concentration, and change over time — the kind of patterns that turn a pile of records into a building's story.

## Data source

NYC Open Data — Open HPD Violations
https://data.cityofnewyork.us/Housing-Development/Open-HPD-Violations/csn4-vhvf/about_data

Dataset ID: `csn4-vhvf`

Queried live via the Socrata API. An app token is optional for public reads but increases the request/throttling allowance. Never commit a real token — see [Setup](#setup).

## Current state

Project notes and progress logs are kept locally (not part of this repo — see Project structure below).

<details>
<summary>Original roadmap (kept for reference — see Current state above for where things actually stand now)</summary>

1. **Data discovery** — schema, scale, date range, building identifiers, violation categories/status. No 2M-row download; aggregate queries only.
2. **Analytical grain** — how reliably can records be grouped into buildings?
3. **Hypothesis testing** — test candidate patterns (recurrence, persistence, trend, concentration) against real aggregated data before assuming any are real.
4. **Visualization build** — narrative notebook/report built around whichever patterns actually held up.
5. **Write-up** — summarizing what the data supports.

</details>

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` (already present, git-ignored) and paste your Socrata app token:

```
SOCRATA_APP_TOKEN=your_token_here
```

## Project structure

```
notebooks/   exploratory and narrative notebooks
docs/        project notes and logs (git-ignored, kept local-only)
src/         shared query/helper code (API client, etc.)
data/        local cached samples (git-ignored, not the full dataset)
```
