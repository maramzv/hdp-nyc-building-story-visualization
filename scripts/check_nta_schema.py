"""Quick check of the NTA neighborhood boundary dataset schema."""
import requests

r = requests.get('https://data.cityofnewyork.us/resource/9nt8-h7nd.json', params={'$limit': 3}, timeout=30)
r.raise_for_status()
rows = r.json()
print(f'{len(rows)} rows')
for row in rows:
    print({k: (v if k != 'the_geom' else str(v)[:100] + '...') for k, v in row.items()})
