"""NOAH Flood Monitoring module.

Mirrors the earthquake (hazards) module architecture:
  store.py      SQLite WAL persistence (PostGIS-shaped schema)
  stations.py   curated real-world station registry
  providers/    external data adapters (base protocol + implementations)
  engine.py     flood-risk classification (NORMAL..CRITICAL)
  ingest.py     polling worker: fetch -> validate -> dedup -> persist -> alert

Data honesty: rainfall observations come from a REAL provider
(Open-Meteo, Copernicus-backed). Water-level and satellite-derived
flood extent are provider interfaces awaiting authorized feeds —
see docs/flood/FLOOD.md.
"""
