# LMEL SAP workbook project

`lmel_sap.json` is an importable project for the existing API Simulator Studio.
It configures the 21 known HTTP method/path pairs from the owner's 2026-11-04
SAP - AVEEVA MES APIs and Endpoint URLs workbook, including GET with JSON
filter payloads. No new endpoint handler or alternate simulator is needed.

The complete 26-entry contract catalog, original payload text, source row
references and workbook SHA256 are maintained by XMES in
`XS_Builder/docs/sap/LMEL_SAP_API_Contracts.md` and its adjacent JSON.
Regenerate both documents and this package using XMES's
`scripts/sap_workbook_contracts.py <workbook> --simulator <this-repo>`.

Start the existing Studio explicitly when needed (the normal suite deliberately
leaves it disabled):

```powershell
.\.venv\Scripts\python.exe .\api_studio\app.py
```

Use Studio's project importer and activate the imported LMEL project, or run
the HTTP verification/import command:

```powershell
.\.venv\Scripts\python.exe .\api_studio\tests\test_lmel_contracts.py --install
```

The script retains existing projects, imports one new copy and activates it.
Subsequent verification omits `--install` to avoid duplicate project copies.
The configured endpoint paths retain the workbook's `/http/` prefix, for
example `GET http://localhost:5050/http/MESSalesOrder` with the supplied JSON
body. Replace only the CPI origin when using the simulator.

Responses are static supplied fixtures. Filters do not change returned rows,
and POST endpoints do not execute real SAP postings. The inspection-lot
payload/direction conflict and raw Atom XML stock-response limitation return
explicit HTTP 501. Three numbered custom APIs and two extra Sales Order entries
lack usable endpoint contracts and are documented without fabricated routes.
Batch classification uses the owner's separate `status`/`message`
acknowledgement fixture; its relationship to the OData response remains open.
Real SAP and whole-MES acceptance are separate. The `/http/` prefix is routed
through the same configurable dispatcher as `/mock/`; no SAP handler is added.
