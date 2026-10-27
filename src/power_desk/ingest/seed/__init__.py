"""Seed data: recorded and synthetic publisher payloads, replayed through the real pipelines.

`data/seed/` holds recorded payloads (ENTSO-E File Library extracts, EIC files); Elexon and
PVLive payloads are synthetic (`synthetic.py`). `replay` serves them in place of the publishers,
`load_seed` runs every source against the replay for the seed week.
"""
