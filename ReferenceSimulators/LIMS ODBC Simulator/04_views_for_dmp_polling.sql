/******************************************************************************
 GNFC LIMS SIMULATOR — 04_views_for_dmp_polling.sql
 ------------------------------------------------------------------------------
 These views are the intended integration surface for the DMP's SQL Server /
 ODBC collector (per Solution Document 3.1.2 — "ODBC/JDBC: Direct relational
 database queries ... for systems that expose tabular data without an API
 layer"). Point the collector's read-only DB login at these views rather than
 the base tables, so LIMS-side schema changes can be absorbed here without
 breaking the DMP's mapping.
******************************************************************************/

USE GNFC_LIMS_SIM;
GO

/* ---- 1. Latest approved result per Plant / Product / Parameter -----------
        This is the "current production quality" snapshot — one row per
        parameter reflecting its most recent lab result and spec status.   */
IF OBJECT_ID('dbo.vw_LatestQualityResults','V') IS NOT NULL DROP VIEW dbo.vw_LatestQualityResults;
GO
CREATE VIEW dbo.vw_LatestQualityResults
AS
WITH Ranked AS (
    SELECT
        p.PlantCode, p.PlantName, p.SiteLocation,
        pr.ProductCode, pr.ProductName,
        tpm.ParameterCode, tpm.ParameterName, tpm.UOM,
        tpm.LSL, tpm.Target, tpm.USL,
        sr.SampleCode, sr.BatchNo, sr.SamplePoint, sr.CollectedDateTime,
        tr.ResultValue, tr.ResultStatus, tr.AnalystName, tr.AnalyzedDateTime,
        tr.IsApproved, tr.ModifiedUTC,
        ROW_NUMBER() OVER (
            PARTITION BY pr.ProductID, tpm.ParameterID
            ORDER BY tr.AnalyzedDateTime DESC
        ) AS rn
    FROM dbo.TestResult tr
    JOIN dbo.SampleRegistration sr ON sr.SampleID = tr.SampleID
    JOIN dbo.Product pr            ON pr.ProductID = sr.ProductID
    JOIN dbo.Plant p               ON p.PlantID = sr.PlantID
    JOIN dbo.TestParameterMaster tpm ON tpm.ParameterID = tr.ParameterID
    WHERE tr.IsApproved = 1
)
SELECT
    PlantCode, PlantName, SiteLocation,
    ProductCode, ProductName,
    ParameterCode, ParameterName, UOM, LSL, Target, USL,
    SampleCode, BatchNo, SamplePoint, CollectedDateTime,
    ResultValue, ResultStatus, AnalystName, AnalyzedDateTime, ModifiedUTC
FROM Ranked
WHERE rn = 1;
GO

/* ---- 2. Quality excursions (Fail / Marginal) for alerting ---------------*/
IF OBJECT_ID('dbo.vw_QualityExcursions','V') IS NOT NULL DROP VIEW dbo.vw_QualityExcursions;
GO
CREATE VIEW dbo.vw_QualityExcursions
AS
SELECT
    p.PlantCode, p.PlantName,
    pr.ProductCode, pr.ProductName,
    tpm.ParameterCode, tpm.ParameterName, tpm.UOM, tpm.LSL, tpm.Target, tpm.USL,
    sr.SampleCode, sr.BatchNo, sr.SamplePoint, sr.CollectedDateTime,
    tr.ResultValue, tr.ResultStatus, tr.AnalystName, tr.AnalyzedDateTime, tr.ModifiedUTC
FROM dbo.TestResult tr
JOIN dbo.SampleRegistration sr   ON sr.SampleID = tr.SampleID
JOIN dbo.Product pr              ON pr.ProductID = sr.ProductID
JOIN dbo.Plant p                 ON p.PlantID = sr.PlantID
JOIN dbo.TestParameterMaster tpm ON tpm.ParameterID = tr.ParameterID
WHERE tr.ResultStatus IN ('Fail','Marginal')
  AND tr.IsApproved = 1;
GO

/* ---- 3. Incremental pull pattern for the DMP collector -------------------
   The collector should NOT re-scan full tables every cycle. Instead it
   keeps a watermark (last successfully processed ModifiedUTC) per table
   and pulls only newer rows, e.g.:

   DECLARE @LastPollUTC DATETIME2(3) = '2026-07-04T10:00:00';  -- from collector's own state store

   SELECT * FROM dbo.TestResult          WHERE ModifiedUTC > @LastPollUTC ORDER BY ModifiedUTC;
   SELECT * FROM dbo.SampleRegistration  WHERE ModifiedUTC > @LastPollUTC ORDER BY ModifiedUTC;

   After each successful pull, the collector advances its watermark to
   MAX(ModifiedUTC) from the returned rows. This is the same "gap
   detection / incremental re-ingestion" pattern described in the Solution
   Document's Completeness/Accuracy/Timeliness checks (4.7.1.2).           */
