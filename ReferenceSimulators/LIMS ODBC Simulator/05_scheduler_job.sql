/******************************************************************************
 GNFC LIMS SIMULATOR — 05_scheduler_job.sql
 ------------------------------------------------------------------------------
 Creates a SQL Server Agent job that runs dbo.usp_RunLIMSSimulationCycle every
 15 minutes, mimicking realistic lab sampling cadence (LIMS results arrive in
 batches through a shift, not as a continuous per-second stream like Historian
 tags). Adjust @freq_subday_interval to change frequency.

 Prerequisite: SQL Server Agent service must be running on the instance.
 Run this script connected to the [msdb] database context, or it will switch
 to msdb itself below.
******************************************************************************/

USE msdb;
GO

IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = N'GNFC_LIMS_Simulator_Cycle')
    EXEC msdb.dbo.sp_delete_job @job_name = N'GNFC_LIMS_Simulator_Cycle';
GO

BEGIN TRANSACTION;

DECLARE @ReturnCode INT = 0;
DECLARE @JobId BINARY(16);

EXEC @ReturnCode = msdb.dbo.sp_add_job
    @job_name        = N'GNFC_LIMS_Simulator_Cycle',
    @enabled         = 1,
    @description     = N'Simulates one LIMS sample-and-result cycle per plant (Urea/Ammonia, Acetic Acid, AN Melt) for the GNFC DMP quality-monitoring demo.',
    @category_name   = N'[Uncategorized (Local)]',
    @owner_login_name= N'sa',
    @job_id          = @JobId OUTPUT;

EXEC @ReturnCode = msdb.dbo.sp_add_jobstep
    @job_id        = @JobId,
    @step_name     = N'Run LIMS Simulation Cycle',
    @subsystem     = N'TSQL',
    @command       = N'EXEC GNFC_LIMS_SIM.dbo.usp_RunLIMSSimulationCycle @ExcursionProbability = 0.05;',
    @database_name = N'GNFC_LIMS_SIM',
    @retry_attempts = 2,
    @retry_interval = 1;

EXEC @ReturnCode = msdb.dbo.sp_add_schedule
    @schedule_name         = N'Every15Minutes',
    @freq_type             = 4,             -- daily
    @freq_interval         = 1,
    @freq_subday_type      = 4,             -- minutes
    @freq_subday_interval  = 15,            -- every 15 minutes
    @active_start_time     = 000000;

EXEC msdb.dbo.sp_attach_schedule
    @job_id        = @JobId,
    @schedule_name = N'Every15Minutes';

EXEC msdb.dbo.sp_add_jobserver
    @job_id      = @JobId,
    @server_name = N'(local)';

COMMIT TRANSACTION;
GO

PRINT 'Job "GNFC_LIMS_Simulator_Cycle" created — runs every 15 minutes once SQL Server Agent is started.';

/* ---- To run one cycle immediately without waiting for the schedule: ----
   EXEC msdb.dbo.sp_start_job @job_name = N'GNFC_LIMS_Simulator_Cycle';
------------------------------------------------------------------------- */
