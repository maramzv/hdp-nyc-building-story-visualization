"""Minimal client for querying the NYC Open Data (Socrata) HPD Violations dataset.

Dataset: Open HPD Violations (csn4-vhvf)
https://data.cityofnewyork.us/Housing-Development/Open-HPD-Violations/csn4-vhvf/about_data
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

DATASET_ID = "csn4-vhvf"
RESOURCE_URL = f"https://data.cityofnewyork.us/resource/{DATASET_ID}.json"
METADATA_URL = f"https://data.cityofnewyork.us/api/views/{DATASET_ID}.json"

APP_TOKEN = os.environ.get("SOCRATA_APP_TOKEN", "")


def _headers() -> dict:
    return {"X-App-Token": APP_TOKEN} if APP_TOKEN else {}


def get_metadata() -> dict:
    """Fetch dataset metadata: columns, types, descriptions, row count estimate."""
    resp = requests.get(METADATA_URL, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def soql_query(select=None, where=None, group=None, order=None, limit=None, timeout=180,
               dataset_id=None) -> list:
    """Run a SoQL query against a Socrata resource endpoint. Returns parsed JSON rows.

    Defaults to the HPD violations dataset (csn4-vhvf); pass dataset_id to query
    a different NYC Open Data dataset (e.g. PLUTO) with the same helper."""
    params = {}
    if select:
        params["$select"] = select
    if where:
        params["$where"] = where
    if group:
        params["$group"] = group
    if order:
        params["$order"] = order
    if limit:
        params["$limit"] = limit

    url = f"https://data.cityofnewyork.us/resource/{dataset_id}.json" if dataset_id else RESOURCE_URL
    resp = requests.get(url, headers=_headers(), params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def row_count(where=None) -> int:
    """Get a total row count (optionally filtered) via a SoQL count aggregate."""
    rows = soql_query(select="count(*) as n", where=where)
    return int(rows[0]["n"]) if rows else 0
