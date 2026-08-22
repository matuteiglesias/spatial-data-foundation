# ADR 0003 — Analytical and display geometry are distinct products

Decision: simplified geometry is never silently reused for spatial assignment, area calculation, or zonal statistics.

Reason: the legacy pipeline used simplified GeoJSONs for some analytical operations. The new system makes that loss of precision impossible by default.
