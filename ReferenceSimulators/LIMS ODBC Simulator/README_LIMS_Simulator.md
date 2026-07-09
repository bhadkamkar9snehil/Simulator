# GNFC LIMS Simulator (SQL Server / T-SQL)

Simulates a LIMS exposing quality data through plain relational tables —
the exact pattern named in the Solution Document (§3.1.2): **"ODBC/JDBC:
Direct relational database queries (SQL Server, Oracle, PostgreSQL, MySQL)
for systems that expose tabular data without an API layer."** No real LIMS
interface exists yet, so this stands in for it until the actual GNFC LIMS
database (or a read replica / reporting view of it) is made available.

Covers the 3 plants currently in scope: **Urea/Ammonia**, **Acetic Acid**,
**AN Melt / Nitrophosphate** (all Bharuch).

## Why this looks different from the Historian/OPC UA simulators

LIMS data is fundamentally not a live tag stream. A sample is drawn, walked
to the lab, analyzed, and approved — results arrive in **batches every
15–60 minutes per shift**, not every second. The simulator and its schema
reflect that: `SampleRegistration` → `TestResult`, populated on a timer, not
a continuous loop.

## Files (run in order)

| File | Purpose |
|---|---|
| `01_create_database_and_schema.sql` | Creates `GNFC_LIMS_SIM` DB and all tables (`Plant`, `Product`, `Shift`, `TestParameterMaster`, `SampleRegistration`, `TestResult`), plus `ModifiedUTC` triggers. |
| `02_seed_master_data.sql` | Seeds the 3 plants, their 4 products, 3 shifts, and 21 QC parameters with LSL/Target/USL spec limits. |
| `03_simulator_procedure.sql` | `usp_SimulateLIMSSample` (one sample + full result set) and `usp_RunLIMSSimulationCycle` (one sample per plant). Includes a ~5% configurable chance of a genuine out-of-spec excursion per parameter, for testing alarm/exception logic. |
| `04_views_for_dmp_polling.sql` | `vw_LatestQualityResults` (current quality snapshot) and `vw_QualityExcursions` (Fail/Marginal only) — point the DMP's read-only DB login at these, not the base tables. |
| `05_scheduler_job.sql` | SQL Server Agent job running `usp_RunLIMSSimulationCycle` every 15 minutes. |

## Quick start

```sql
-- 1. Run files 01 through 04 in order in SSMS/Azure Data Studio.
-- 2. Generate a few cycles manually to see data flow:
EXEC GNFC_LIMS_SIM.dbo.usp_RunLIMSSimulationCycle;
GO 5   -- run 5 times (SSMS batch-repeat) to build up history

-- 3. Check the live quality snapshot:
SELECT * FROM GNFC_LIMS_SIM.dbo.vw_LatestQualityResults ORDER BY PlantCode, ProductCode, ParameterCode;

-- 4. Check for any quality excursions:
SELECT * FROM GNFC_LIMS_SIM.dbo.vw_QualityExcursions ORDER BY AnalyzedDateTime DESC;

-- 5. (Optional) Install the recurring job once SQL Server Agent is running:
--    run 05_scheduler_job.sql
```

## How the DMP should integrate against this (and later, the real LIMS)

- Use a **read-only SQL login** scoped to `GNFC_LIMS_SIM` (or the two views only).
- Poll `dbo.vw_LatestQualityResults` on a schedule (e.g. every 5–15 min) for
  the dashboard's "current production quality" panels.
- Poll `dbo.vw_QualityExcursions` for alerting / exception workflows, feeding
  the same anomaly/exception pipeline described for Historian data quality
  (Solution Document §4.7.1.4).
- For incremental pulls instead of full-table scans, filter both base tables
  on `ModifiedUTC > @LastPollUTC` (watermark pattern) — see the example query
  at the bottom of `04_views_for_dmp_polling.sql`.
- When the real LIMS/SQL Server (or its reporting replica) becomes available,
  the collector's connection string and table/view names are the only things
  that change, provided GNFC's actual schema is mapped onto (or aliased to)
  the same column names during the joint design phase called out in the SoW.

## Customizing

- **Spec limits**: edit `LSL` / `Target` / `USL` in `TestParameterMaster` to
  match GNFC's actual approved specification sheets.
- **Excursion rate**: pass `@ExcursionProbability` to
  `usp_RunLIMSSimulationCycle` (default 0.05 = 5% of results per cycle land
  out of spec) — raise it temporarily to stress-test alerting.
- **Sampling frequency**: change `@freq_subday_interval` in
  `05_scheduler_job.sql` (currently 15 minutes).
- **More products/plants**: add rows to `Plant` / `Product` /
  `TestParameterMaster`, then extend `usp_RunLIMSSimulationCycle` with an
  additional `EXEC usp_SimulateLIMSSample @PlantCode='...'` line.
