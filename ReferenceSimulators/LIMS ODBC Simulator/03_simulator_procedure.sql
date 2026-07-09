/******************************************************************************
 GNFC LIMS SIMULATOR — 03_simulator_procedure.sql
 ------------------------------------------------------------------------------
 Two procedures:

   dbo.usp_SimulateLIMSSample        Registers ONE sample for a given plant
                                      (random product if not specified),
                                      generates results for every active test
                                      parameter of that product, and approves
                                      the sample. Values are generated around
                                      each parameter's Target with realistic
                                      noise, plus a configurable chance of a
                                      genuine out-of-spec excursion — useful
                                      for testing the DMP's quality-alarm /
                                      exception-workflow logic.

   dbo.usp_RunLIMSSimulationCycle    Convenience wrapper that draws one sample
                                      per plant (3 plants -> 3 samples) in a
                                      single call. This is what the SQL Agent
                                      job (see 05_scheduler_job.sql) executes
                                      on a schedule to mimic real lab sampling
                                      cadence (typically every 15-60 minutes,
                                      NOT a per-second tag stream).
******************************************************************************/

USE GNFC_LIMS_SIM;
GO

IF OBJECT_ID('dbo.usp_SimulateLIMSSample','P') IS NOT NULL
    DROP PROCEDURE dbo.usp_SimulateLIMSSample;
GO
CREATE PROCEDURE dbo.usp_SimulateLIMSSample
    @PlantCode            VARCHAR(20),
    @ProductCode          VARCHAR(30)   = NULL,   -- NULL = pick a random active product for the plant
    @ExcursionProbability DECIMAL(5,4) = 0.05,    -- ~5% of parameter results land out of spec
    @SampleType           VARCHAR(30)   = 'Finished Product',
    @SampleID_OUT         BIGINT        = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @PlantID   INT = (SELECT PlantID FROM dbo.Plant WHERE PlantCode = @PlantCode);
    IF @PlantID IS NULL
    BEGIN
        RAISERROR('Unknown PlantCode: %s', 16, 1, @PlantCode);
        RETURN;
    END

    DECLARE @ProductID INT;
    IF @ProductCode IS NOT NULL
        SET @ProductID = (SELECT ProductID FROM dbo.Product WHERE ProductCode = @ProductCode AND PlantID = @PlantID);
    ELSE
        SELECT TOP 1 @ProductID = ProductID
        FROM dbo.Product
        WHERE PlantID = @PlantID
        ORDER BY NEWID();                          -- random product for this plant

    IF @ProductID IS NULL
    BEGIN
        RAISERROR('No matching product found for plant %s / product %s', 16, 1, @PlantCode, @ProductCode);
        RETURN;
    END

    /* ---- Shift lookup from current server time ---- */
    DECLARE @Hour INT = DATEPART(HOUR, GETDATE());
    DECLARE @ShiftID INT = (
        SELECT ShiftID FROM dbo.Shift
        WHERE (@Hour >= 6  AND @Hour < 14 AND ShiftCode='A')
           OR (@Hour >= 14 AND @Hour < 22 AND ShiftCode='B')
           OR ((@Hour >= 22 OR @Hour < 6) AND ShiftCode='C')
    );

    DECLARE @Now        DATETIME2(3) = SYSDATETIME();
    DECLARE @Collected  DATETIME2(3) = DATEADD(MINUTE, -1 * (5 + ABS(CHECKSUM(NEWID())) % 20), @Now); -- sample drawn 5-25 min ago
    DECLARE @Received   DATETIME2(3) = DATEADD(MINUTE, 2, @Collected);
    DECLARE @Analyzed   DATETIME2(3) = @Now;
    DECLARE @SampleCode VARCHAR(40)  = CONCAT(@PlantCode, '-', FORMAT(@Now,'yyyyMMddHHmmssfff'));

    INSERT INTO dbo.SampleRegistration
        (SampleCode, PlantID, ProductID, BatchNo, ShiftID, SamplePoint, SampleType,
         CollectedDateTime, ReceivedDateTime, Status)
    VALUES
        (@SampleCode, @PlantID, @ProductID,
         CONCAT('B', FORMAT(@Now,'yyyyMMdd'), '-', RIGHT('000' + CAST(1+ABS(CHECKSUM(NEWID()))%40 AS VARCHAR(3)),3)),
         @ShiftID, 'Product Discharge / Bagging Point', @SampleType,
         @Collected, @Received, 'InAnalysis');

    DECLARE @SampleID BIGINT = SCOPE_IDENTITY();
    SET @SampleID_OUT = @SampleID;

    DECLARE @AnalystName VARCHAR(50) =
        (SELECT TOP 1 v FROM (VALUES ('R. Patel'),('S. Iyer'),('M. Shaikh'),('A. Verma'),('K. Nair')) t(v) ORDER BY NEWID());
    DECLARE @ApprovedBy VARCHAR(50) =
        (SELECT TOP 1 v FROM (VALUES ('Shift Chemist'),('QC Officer'),('Lab In-charge')) t(v) ORDER BY NEWID());

    /* ---- Generate one result per active parameter of this product ----
       Value = Target + (CLT-ish noise in roughly [-1,1]) * 0.25 * half-band
       Excursion (prob = @ExcursionProbability) pushes the value 15-30% past
       the half-band beyond whichever limit is breached, simulating a real
       quality deviation for alarm/workflow testing.                       */
    INSERT INTO dbo.TestResult
        (SampleID, ParameterID, ResultValue, UOM, ResultStatus,
         AnalystName, InstrumentID, AnalyzedDateTime, IsApproved, ApprovedBy, ApprovedDateTime)
    SELECT
        @SampleID,
        tpm.ParameterID,
        ROUND(gen.ResultValue, 4),
        tpm.UOM,
        CASE
            WHEN tpm.LSL IS NOT NULL AND gen.ResultValue < tpm.LSL THEN 'Fail'
            WHEN tpm.USL IS NOT NULL AND gen.ResultValue > tpm.USL THEN 'Fail'
            WHEN tpm.LSL IS NOT NULL
                 AND gen.ResultValue < tpm.LSL + 0.10 * (gen.HalfBand * 2) THEN 'Marginal'
            WHEN tpm.USL IS NOT NULL
                 AND gen.ResultValue > tpm.USL - 0.10 * (gen.HalfBand * 2) THEN 'Marginal'
            ELSE 'Pass'
        END,
        @AnalystName,
        CONCAT('INSTR-', RIGHT('000' + CAST(1 + ABS(CHECKSUM(NEWID())) % 12 AS VARCHAR(3)), 3)),
        @Analyzed,
        1,
        @ApprovedBy,
        @Analyzed
    FROM dbo.TestParameterMaster tpm
    CROSS APPLY (
        SELECT
            gen1.MidPoint,
            gen1.HalfBand,
            CASE
                WHEN (ABS(CHECKSUM(NEWID())) % 10000) / 10000.0 < @ExcursionProbability
                THEN gen1.MidPoint
                     + (CASE WHEN ABS(CHECKSUM(NEWID())) % 2 = 0 THEN 1 ELSE -1 END)
                       * gen1.HalfBand
                       * (1.15 + ((ABS(CHECKSUM(NEWID())) % 10000) / 10000.0) * 0.15)  -- 15%-30% beyond limit
                ELSE
                     gen1.MidPoint
                     + ( ( ((ABS(CHECKSUM(NEWID())) % 10000) / 10000.0)
                         + ((ABS(CHECKSUM(NEWID())) % 10000) / 10000.0)
                         + ((ABS(CHECKSUM(NEWID())) % 10000) / 10000.0)
                         - 1.5 ) / 1.5 )                                   -- ~ triangular noise in [-1,1]
                       * gen1.HalfBand * 0.5
            END AS ResultValue
        FROM (
            SELECT
                MidPoint = ISNULL(tpm.Target,
                              (ISNULL(tpm.LSL, ISNULL(tpm.USL,1) * 0.9)
                             + ISNULL(tpm.USL, ISNULL(tpm.LSL,1) * 1.1)) / 2.0),
                HalfBand = CASE
                              WHEN tpm.LSL IS NOT NULL AND tpm.USL IS NOT NULL
                                   THEN (tpm.USL - tpm.LSL) / 2.0
                              WHEN tpm.USL IS NOT NULL AND tpm.Target IS NOT NULL
                                   THEN (tpm.USL - tpm.Target)
                              WHEN tpm.LSL IS NOT NULL AND tpm.Target IS NOT NULL
                                   THEN (tpm.Target - tpm.LSL)
                              ELSE ISNULL(tpm.Target,1) * 0.1
                           END
        ) gen1
    ) gen
    WHERE tpm.ProductID = @ProductID AND tpm.IsActive = 1;

    UPDATE dbo.SampleRegistration
       SET Status = 'Approved'
     WHERE SampleID = @SampleID;
END
GO

IF OBJECT_ID('dbo.usp_RunLIMSSimulationCycle','P') IS NOT NULL
    DROP PROCEDURE dbo.usp_RunLIMSSimulationCycle;
GO
CREATE PROCEDURE dbo.usp_RunLIMSSimulationCycle
    @ExcursionProbability DECIMAL(5,4) = 0.05
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @SampleID BIGINT;

    EXEC dbo.usp_SimulateLIMSSample @PlantCode='UREA_AMM', @ExcursionProbability=@ExcursionProbability, @SampleID_OUT=@SampleID OUTPUT;
    EXEC dbo.usp_SimulateLIMSSample @PlantCode='ACETIC',   @ExcursionProbability=@ExcursionProbability, @SampleID_OUT=@SampleID OUTPUT;
    EXEC dbo.usp_SimulateLIMSSample @PlantCode='ANMELT',   @ExcursionProbability=@ExcursionProbability, @SampleID_OUT=@SampleID OUTPUT;

    PRINT CONCAT('LIMS simulation cycle completed at ', CONVERT(VARCHAR, SYSDATETIME(), 120));
END
GO

/* ---- One-off manual test (comment out before scheduling in production) --
EXEC dbo.usp_RunLIMSSimulationCycle;
SELECT TOP 20 * FROM dbo.SampleRegistration ORDER BY SampleID DESC;
SELECT TOP 50 * FROM dbo.TestResult ORDER BY ResultID DESC;
-----------------------------------------------------------------------------*/
