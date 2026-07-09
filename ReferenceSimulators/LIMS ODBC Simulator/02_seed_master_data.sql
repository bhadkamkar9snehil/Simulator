/******************************************************************************
 GNFC LIMS SIMULATOR — 02_seed_master_data.sql
 ------------------------------------------------------------------------------
 Seeds Plant / Product / Shift / TestParameterMaster for the 3 in-scope plants.
 Spec limits below are illustrative, typical-industry QC bands for demo
 purposes only (per Evaluation Criteria: "dummy data allowed for demo") —
 replace with GNFC's actual approved specification sheet per product during
 real integration.
******************************************************************************/

USE GNFC_LIMS_SIM;
GO
SET NOCOUNT ON;

/* ---------- Plants -------------------------------------------------------*/
INSERT INTO dbo.Plant (PlantCode, PlantName, SiteLocation, DCSVendor) VALUES
 ('UREA_AMM',  'Urea / Ammonia',                   'Bharuch', 'Yokogawa'),
 ('ACETIC',    'Acetic Acid',                      'Bharuch', 'Honeywell'),
 ('ANMELT',    'Ammonium Nitrophosphate / AN Melt','Bharuch', 'Yokogawa');
GO

/* ---------- Shifts --------------------------------------------------------*/
INSERT INTO dbo.Shift (ShiftCode, ShiftName, StartTime, EndTime) VALUES
 ('A', 'Shift A (06-14)', '06:00', '14:00'),
 ('B', 'Shift B (14-22)', '14:00', '22:00'),
 ('C', 'Shift C (22-06)', '22:00', '06:00');
GO

/* ---------- Products ------------------------------------------------------*/
INSERT INTO dbo.Product (PlantID, ProductCode, ProductName, DefaultUOM)
SELECT PlantID, 'UREA_PRILL', 'Urea (Prilled)', '%' FROM dbo.Plant WHERE PlantCode='UREA_AMM';
INSERT INTO dbo.Product (PlantID, ProductCode, ProductName, DefaultUOM)
SELECT PlantID, 'NH3_LIQ', 'Ammonia (Liquid)', '%' FROM dbo.Plant WHERE PlantCode='UREA_AMM';

INSERT INTO dbo.Product (PlantID, ProductCode, ProductName, DefaultUOM)
SELECT PlantID, 'ACOH_GLACIAL', 'Acetic Acid (Glacial)', '%' FROM dbo.Plant WHERE PlantCode='ACETIC';

INSERT INTO dbo.Product (PlantID, ProductCode, ProductName, DefaultUOM)
SELECT PlantID, 'ANP_MELT', 'Ammonium Nitrophosphate (AN Melt / NPK 20:20:0:13)', '%' FROM dbo.Plant WHERE PlantCode='ANMELT';
GO

/* ---------- Test Parameters: Urea (Prilled) --------------------------------
   LSL / Target / USL                                                       */
DECLARE @P INT = (SELECT ProductID FROM dbo.Product WHERE ProductCode='UREA_PRILL');
INSERT INTO dbo.TestParameterMaster (ProductID, ParameterCode, ParameterName, UOM, LSL, Target, USL, TestMethod) VALUES
 (@P, 'N_CONTENT',   'Total Nitrogen Content',       '%',   46.0,  46.3,  46.6, 'IS 12995 / Kjeldahl'),
 (@P, 'BIURET',      'Biuret Content',               '%',    NULL,  0.60,  1.00, 'IS 12995'),
 (@P, 'MOISTURE',    'Moisture',                     '%',    NULL,  0.30,  0.50, 'Karl Fischer'),
 (@P, 'FREE_NH3',    'Free Ammonia',                 'ppm',  NULL,  100,   150,  'Titration'),
 (@P, 'CRUSH_STR',   'Crushing Strength',             'kg',   2.0,   3.5,  NULL, 'Hardness Tester'),
 (@P, 'PARTICLE_SZ', 'Particle Size (1-4 mm)',       '%',   90.0,  95.0, 100.0, 'Sieve Analysis');

/* ---------- Test Parameters: Ammonia (Liquid) ------------------------------*/
DECLARE @P2 INT = (SELECT ProductID FROM dbo.Product WHERE ProductCode='NH3_LIQ');
INSERT INTO dbo.TestParameterMaster (ProductID, ParameterCode, ParameterName, UOM, LSL, Target, USL, TestMethod) VALUES
 (@P2, 'PURITY',    'Ammonia Purity',   '%',   99.50, 99.80, 100.00, 'GC'),
 (@P2, 'MOISTURE',  'Moisture',         'ppm', NULL,  100,   150,    'Karl Fischer'),
 (@P2, 'OIL_CONT',  'Oil Content',      'ppm', NULL,  3,     5,      'IR Spectroscopy');

/* ---------- Test Parameters: Acetic Acid (Glacial) -------------------------*/
DECLARE @P3 INT = (SELECT ProductID FROM dbo.Product WHERE ProductCode='ACOH_GLACIAL');
INSERT INTO dbo.TestParameterMaster (ProductID, ParameterCode, ParameterName, UOM, LSL, Target, USL, TestMethod) VALUES
 (@P3, 'PURITY',      'Acetic Acid Purity',   '%',   99.70, 99.85, 100.00, 'GC / Titration'),
 (@P3, 'WATER_CONT',  'Water Content',        '%',   NULL,  0.10,  0.15,   'Karl Fischer'),
 (@P3, 'FORMIC_ACID', 'Formic Acid',          'ppm', NULL,  100,   150,    'GC'),
 (@P3, 'IRON_CONT',   'Iron Content',         'ppm', NULL,  0.5,   1.0,    'AAS'),
 (@P3, 'COLOR_APHA',  'Color',                'APHA',NULL,  5,     10,     'Colorimeter'),
 (@P3, 'KMNO4_TIME',  'Permanganate Time',    'min', 30,    60,    NULL,   'Wet Chemistry'),
 (@P3, 'ACETALDEHYDE','Acetaldehyde Content', 'ppm', NULL,  10,    15,     'GC');

/* ---------- Test Parameters: AN Melt / Nitrophosphate ----------------------*/
DECLARE @P4 INT = (SELECT ProductID FROM dbo.Product WHERE ProductCode='ANP_MELT');
INSERT INTO dbo.TestParameterMaster (ProductID, ParameterCode, ParameterName, UOM, LSL, Target, USL, TestMethod) VALUES
 (@P4, 'N_CONTENT',   'Total Nitrogen Content',  '%',      19.5, 20.0, 20.5,  'Kjeldahl'),
 (@P4, 'MOISTURE',    'Moisture',                '%',      NULL, 1.0,  1.5,   'Karl Fischer'),
 (@P4, 'FREE_ACID',   'Free Acid (as HNO3)',     '%',      NULL, 0.20, 0.30,  'Titration'),
 (@P4, 'PARTICLE_SZ', 'Particle Size (2-4 mm)',  '%',      90.0, 95.0, 100.0, 'Sieve Analysis'),
 (@P4, 'BULK_DENSITY','Bulk Density',            'kg/m3',  900,  950,  1000,  'Density Cup'),
 (@P4, 'OIL_COATING', 'Oil Coating',             '%',      NULL, 0.50, 0.80,  'Extraction Method');
GO

PRINT 'Master data seeded: 3 plants, 4 products, 3 shifts, 21 test parameters.';
