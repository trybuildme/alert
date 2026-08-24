# Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Health says STALE | provider unreachable / rate-limited | check backend log for `provider usgs failed`; worker backs off automatically (30s→8min cap) |
| Map layer empty but health LIVE | magnitude filter above current activity | lower Min magnitude slider; widen `EARTHQUAKE_BBOX` |
| No SSE updates | proxy buffering | nginx: `proxy_buffering off` on the stream path |
| 400 Bad Request from USGS | malformed EARTHQUAKE_BBOX | keep order minlon,minlat,maxlon,maxlat |
| DB locked errors | external process holding sqlite file | stop other backend instances sharing NOAH_EQ_DB |
