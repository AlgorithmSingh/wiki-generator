"""Phase 3 retrieval lanes. Each module exposes ``run(bundle, section, options)``.

Lanes are pure: they read the loaded bundle and a single SectionPlan and return
a ``LaneResult`` of raw hits + unresolved rows. They never write to disk.
"""
from __future__ import annotations
