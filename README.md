# Power Desk ⚡

A high-density minimalist analyst dashboard for UK Power & Energy Data.

## Features
- **ELT Pipeline (`dlt`):** Elexon BMRS source builder with raw data preservation and incremental merge on natural keys.
- **DBT-style Modeling:** DuckDB SQL Views for ODS and Marts with settlement period to UTC natural key resolution.
- **Analyst Terminal Grid:** Draggable, resizable cards powered by GridStack.js.
- **Open-Source Lineage:** DAG visualization via Cytoscape.js and Dagre.
- **Functional Energy Palette:** Meaningful colors for generation fuels (Wind, Solar, Nuclear, CCGT, Demand, Forecast).
- **Agent Widget Skill:** Extensible `.agents/skills/create-widget/SKILL.md` allowing AI agents to generate and mount new analytical cards.
