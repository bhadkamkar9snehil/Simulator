/******************************************************************************
 GNFC LIMS SIMULATOR — 01_create_database_and_schema.sql
 ------------------------------------------------------------------------------
 Purpose : Stand-in for a real LIMS, exposing quality/lab data through plain
           SQL Server tables — exactly the integration pattern named in the
           Historian/DMP Solution Document (Section 3.1.2, "ODBC/JDBC: Direct
           relational database queries ... for systems that expose tabular
           data without an API layer"). The DMP's SQL Server/ODBC collector
           can point at this schema today and be repointed at the real LIMS
           database later with zero logic change, provided table/column names
           are aligned during integration design.

 Scope   : 3 plants per current SoW scope —
             1. Urea / Ammonia            (Bharuch)
             2. Acetic Acid                (Bharuch)
             3. Ammonium Nitrophosphate / AN Melt (Bharuch)

 Run as  : A SQL Server login with CREATE DATABASE / dbcreator rights.
 Order   : Run files 01 -> 05 in sequence.
******************************************************************************/

SET NOCOUNT ON;
GO

IF DB_ID(N'GNFC_LIMS_SIM') IS NULL
BEGIN
    CREATE DATABASE GNFC_LIMS_SIM;
END
GO

USE GNFC_LIMS_SIM;
GO

/* ---------- Master: Plant ------------------------------------------------ */
IF OBJECT_ID('dbo.Plant','U') IS NOT NULL DROP TABLE dbo.Plant;
GO
CREATE TABLE dbo.Plant
(
    PlantID       INT IDENTITY(1,1) PRIMARY KEY,
    PlantCode     VARCHAR(20)  NOT NULL UNIQUE,
    PlantName     VARCHAR(100) NOT NULL,
    SiteLocation  VARCHAR(50)  NOT NULL,
    DCSVendor     VARCHAR(50)  NULL          -- for cross-reference with Historian tag source
);
GO

/* ---------- Master: Product ---------------------------------------------- */
IF OBJECT_ID('dbo.Product','U') IS NOT NULL DROP TABLE dbo.Product;
GO
CREATE TABLE dbo.Product
(
    ProductID     INT IDENTITY(1,1) PRIMARY KEY,
    PlantID       INT NOT NULL REFERENCES dbo.Plant(PlantID),
    ProductCode   VARCHAR(30)  NOT NULL UNIQUE,
    ProductName   VARCHAR(100) NOT NULL,
    DefaultUOM    VARCHAR(20)  NULL
);
GO

/* ---------- Master: Shift -------------------------------------------------*/
IF OBJECT_ID('dbo.Shift','U') IS NOT NULL DROP TABLE dbo.Shift;
GO
CREATE TABLE dbo.Shift
(
    ShiftID    INT IDENTITY(1,1) PRIMARY KEY,
    ShiftCode  VARCHAR(10) NOT NULL UNIQUE,
    ShiftName  VARCHAR(20) NOT NULL,
    StartTime  TIME NOT NULL,
    EndTime    TIME NOT NULL
);
GO

/* ---------- Master: Test Parameter (per product spec/limits) -------------*/
IF OBJECT_ID('dbo.TestParameterMaster','U') IS NOT NULL DROP TABLE dbo.TestParameterMaster;
GO
CREATE TABLE dbo.TestParameterMaster
(
    ParameterID    INT IDENTITY(1,1) PRIMARY KEY,
    ProductID      INT NOT NULL REFERENCES dbo.Product(ProductID),
    ParameterCode  VARCHAR(30)  NOT NULL,
    ParameterName  VARCHAR(100) NOT NULL,
    UOM            VARCHAR(20)  NOT NULL,
    LSL            DECIMAL(10,4) NULL,        -- Lower Spec Limit (NULL = no lower limit)
    Target         DECIMAL(10,4) NULL,
    USL            DECIMAL(10,4) NULL,        -- Upper Spec Limit (NULL = no upper limit)
    TestMethod     VARCHAR(100)  NULL,
    IsActive       BIT NOT NULL DEFAULT 1,
    CONSTRAINT UQ_Product_ParameterCode UNIQUE (ProductID, ParameterCode)
);
GO

/* ---------- Transaction: Sample Registration ------------------------------
   One row per physical sample drawn and logged in the LIMS.                */
IF OBJECT_ID('dbo.SampleRegistration','U') IS NOT NULL DROP TABLE dbo.SampleRegistration;
GO
CREATE TABLE dbo.SampleRegistration
(
    SampleID           BIGINT IDENTITY(1,1) PRIMARY KEY,
    SampleCode         VARCHAR(40)  NOT NULL UNIQUE,      -- LIMS barcode/ID
    PlantID            INT NOT NULL REFERENCES dbo.Plant(PlantID),
    ProductID          INT NOT NULL REFERENCES dbo.Product(ProductID),
    BatchNo            VARCHAR(30)  NULL,
    ShiftID            INT NULL REFERENCES dbo.Shift(ShiftID),
    SamplePoint        VARCHAR(100) NULL,                 -- e.g. "Prilling Tower Outlet"
    SampleType         VARCHAR(30)  NOT NULL DEFAULT 'Finished Product', -- RM / Inprocess / Finished Product
    CollectedDateTime  DATETIME2(3) NOT NULL,
    ReceivedDateTime   DATETIME2(3) NULL,
    Status             VARCHAR(20)  NOT NULL DEFAULT 'Registered',
                        -- Registered -> InAnalysis -> Completed -> Approved / Rejected
    CreatedUTC         DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    ModifiedUTC        DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);
GO
CREATE INDEX IX_SampleRegistration_ModifiedUTC ON dbo.SampleRegistration(ModifiedUTC);
CREATE INDEX IX_SampleRegistration_Plant_Product ON dbo.SampleRegistration(PlantID, ProductID, CollectedDateTime);
GO

/* ---------- Transaction: Test Result --------------------------------------
   One row per parameter result against a sample.                          */
IF OBJECT_ID('dbo.TestResult','U') IS NOT NULL DROP TABLE dbo.TestResult;
GO
CREATE TABLE dbo.TestResult
(
    ResultID          BIGINT IDENTITY(1,1) PRIMARY KEY,
    SampleID          BIGINT NOT NULL REFERENCES dbo.SampleRegistration(SampleID),
    ParameterID       INT    NOT NULL REFERENCES dbo.TestParameterMaster(ParameterID),
    ResultValue       DECIMAL(10,4) NOT NULL,
    UOM               VARCHAR(20)   NOT NULL,
    ResultStatus      VARCHAR(15)   NOT NULL,   -- Pass / Fail / Marginal
    AnalystName       VARCHAR(50)   NULL,
    InstrumentID      VARCHAR(30)   NULL,
    AnalyzedDateTime  DATETIME2(3)  NOT NULL,
    IsApproved        BIT NOT NULL DEFAULT 0,
    ApprovedBy        VARCHAR(50)   NULL,
    ApprovedDateTime  DATETIME2(3)  NULL,
    CreatedUTC        DATETIME2(3)  NOT NULL DEFAULT SYSUTCDATETIME(),
    ModifiedUTC       DATETIME2(3)  NOT NULL DEFAULT SYSUTCDATETIME()
);
GO
CREATE INDEX IX_TestResult_ModifiedUTC ON dbo.TestResult(ModifiedUTC);
CREATE INDEX IX_TestResult_SampleID ON dbo.TestResult(SampleID);
GO

/* ---------- Triggers: keep ModifiedUTC current on UPDATE ------------------
   This is the watermark column the DMP's ODBC/JDBC collector will poll on
   (WHERE ModifiedUTC > @LastPollUTC) instead of re-scanning full tables.   */
IF OBJECT_ID('dbo.trg_SampleRegistration_ModifiedUTC','TR') IS NOT NULL
    DROP TRIGGER dbo.trg_SampleRegistration_ModifiedUTC;
GO
CREATE TRIGGER dbo.trg_SampleRegistration_ModifiedUTC
ON dbo.SampleRegistration
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE sr
       SET ModifiedUTC = SYSUTCDATETIME()
    FROM dbo.SampleRegistration sr
    INNER JOIN inserted i ON sr.SampleID = i.SampleID;
END
GO

IF OBJECT_ID('dbo.trg_TestResult_ModifiedUTC','TR') IS NOT NULL
    DROP TRIGGER dbo.trg_TestResult_ModifiedUTC;
GO
CREATE TRIGGER dbo.trg_TestResult_ModifiedUTC
ON dbo.TestResult
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE tr
       SET ModifiedUTC = SYSUTCDATETIME()
    FROM dbo.TestResult tr
    INNER JOIN inserted i ON tr.ResultID = i.ResultID;
END
GO

PRINT 'Schema created: Plant, Product, Shift, TestParameterMaster, SampleRegistration, TestResult';
