# Data Sources

## USGS (live)
FDSN event service, GeoJSON: `https://earthquake.usgs.gov/fdsnws/event/1/query`
- Bounding box via `EARTHQUAKE_BBOX` (`minlon,minlat,maxlon,maxlat`; default Philippines `115,4,127,21`, empty = global)
- Magnitude floor `EARTHQUAKE_MIN_MAGNITUDE` (default 2.5), lookback `EARTHQUAKE_LOOKBACK_MINUTES` (default 180)
- Original payload preserved in `raw_json` for audit.

## PHIVOLCS (requires configuration — do not enable blindly)
No stable official machine-readable feed is published; the provider stub
(`app/hazards/providers/phivolcs.py`) exists as a first-class slot.
When an official source is agreed: implement `fetch_recent()`, return
normalized HazardEvents. Health reports "requires-configuration" until then.

## Future providers
Implement `HazardProvider.fetch_recent(lookback_minutes, min_magnitude)`
and register in `main.py`. Local/IoT sensors should wrap their gateway in
the same interface. Dedup keys are `(provider, provider_event_id)`.
