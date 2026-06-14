param([Parameter(Mandatory=$true)][string]$PayloadPath)
$ErrorActionPreference = "Stop"
function Out-Json($obj) { $obj | ConvertTo-Json -Depth 30 -Compress }
function Clean-Part([string]$v, [string]$default) {
  if ([string]::IsNullOrWhiteSpace($v)) { return $default }
  return ($v -replace "[^A-Za-z0-9_]", "_")
}
try {
  $payload = Get-Content -Raw -LiteralPath $PayloadPath | ConvertFrom-Json
  $server = [string]$payload.server
  $port = [string]$payload.port
  $database = [string]$payload.database
  $auth = [string]$payload.auth
  $username = [string]$payload.username
  $password = [string]$payload.password
  $table = [string]$payload.table
  $encrypt = if ($payload.encrypt) { "True" } else { "False" }
  $trust = if ($payload.trust_server_certificate) { "True" } else { "False" }
  if ([string]::IsNullOrWhiteSpace($server)) { $server = "localhost" }
  if ([string]::IsNullOrWhiteSpace($port)) { $port = "1433" }
  if ([string]::IsNullOrWhiteSpace($database)) { $database = "master" }
  if ([string]::IsNullOrWhiteSpace($table)) { $table = "dbo.tag_snapshots" }
  $serverPart = "$server,$port"
  if ($auth -eq "windows") {
    $cs = "Server=$serverPart;Database=$database;Integrated Security=True;Encrypt=$encrypt;TrustServerCertificate=$trust;Connection Timeout=8"
  } else {
    $cs = "Server=$serverPart;Database=$database;User ID=$username;Password=$password;Encrypt=$encrypt;TrustServerCertificate=$trust;Connection Timeout=8"
  }
  Add-Type -AssemblyName System.Data
  $conn = New-Object System.Data.SqlClient.SqlConnection $cs
  $conn.Open()
  $action = [string]$payload.action

  if ($action -eq "list_databases") {
    $cmd = $conn.CreateCommand()
    $cmd.CommandText = "SELECT name FROM sys.databases WHERE state_desc='ONLINE' ORDER BY name"
    $reader = $cmd.ExecuteReader()
    $items = @()
    while ($reader.Read()) { $items += [string]$reader.GetValue(0) }
    $reader.Close(); $conn.Close()
    Out-Json @{ ok=$true; databases=$items }
    exit 0
  }

  if ($action -eq "list_tables") {
    $cmd = $conn.CreateCommand()
    $cmd.CommandText = "SELECT TABLE_SCHEMA + '.' + TABLE_NAME AS table_name FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_SCHEMA, TABLE_NAME"
    $reader = $cmd.ExecuteReader()
    $items = @()
    while ($reader.Read()) { $items += [string]$reader.GetValue(0) }
    $reader.Close(); $conn.Close()
    Out-Json @{ ok=$true; database=$database; tables=$items }
    exit 0
  }

  $safe = $table.Replace("[", "").Replace("]", "").Split(".") | Where-Object { $_ -ne "" }
  if ($safe.Count -ge 2) { $schema = $safe[$safe.Count-2]; $name = $safe[$safe.Count-1] } else { $schema = "dbo"; $name = $safe[0] }
  $schema = Clean-Part $schema "dbo"
  $name = Clean-Part $name "tag_snapshots"
  $tableSql = "[$schema].[$name]"
  $objectId = "$schema.$name"
  $cmd = $conn.CreateCommand()
  $cmd.CommandText = "IF OBJECT_ID(N'$objectId', N'U') IS NULL BEGIN CREATE TABLE $tableSql (id BIGINT IDENTITY(1,1) PRIMARY KEY, ts NVARCHAR(64) NOT NULL, tag_name NVARCHAR(255) NOT NULL, value NVARCHAR(MAX) NULL, unit NVARCHAR(64) NULL, quality NVARCHAR(64) NULL, description NVARCHAR(MAX) NULL) END"
  [void]$cmd.ExecuteNonQuery()
  $rowsWritten = 0
  if ($action -eq "write" -and $payload.rows) {
    foreach ($r in $payload.rows) {
      $ins = $conn.CreateCommand()
      $ins.CommandText = "INSERT INTO $tableSql (ts, tag_name, value, unit, quality, description) VALUES (@ts, @tag_name, @value, @unit, @quality, @description)"
      foreach ($p in @("ts","tag_name","value","unit","quality","description")) {
        $param = $ins.Parameters.Add("@$p", [System.Data.SqlDbType]::NVarChar, -1)
        $param.Value = [string]$r.$p
      }
      [void]$ins.ExecuteNonQuery()
      $rowsWritten++
    }
  }
  $conn.Close()
  Out-Json @{ ok=$true; message="MSSQL connection OK"; database=$database; table=$objectId; rows_written=$rowsWritten }
  exit 0
} catch {
  Out-Json @{ ok=$false; error=$_.Exception.Message }
  exit 1
}
