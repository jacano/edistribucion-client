# Architecture and Aura flows

This file explains the technical steps the tool takes against the e-distribucion
private area (zonaprivada.edistribucion.com). The portal runs on Salesforce
Experience Cloud, so the client talks to the Aura endpoint.

The diagrams use [Mermaid](https://mermaid.js.org/). GitHub shows them in this
file.

## 1. Overview

```mermaid
flowchart LR
    CLI["CLI (main)"] --> Client["Client (HTTP + Aura)"]
    Client --> Session["Session (sid cookie)"]
    Client --> Portal["Portal (Aura)"]
    Client --> Zip["ZIP (hourly CSV)"]
    Zip --> Reader["read_zip_rows"]
    Reader --> Hours["hours: (day, hour) to (kWh, real)"]
    Hours --> Agg["aggregate"]
    Agg --> Report["report (text or JSON)"]
```

- `Session` keeps the `sid` cookie and writes `session.json`.
- `Client` does the HTTP work and the Aura calls.
- The data comes as one ZIP. The tool reads the CSV rows and builds the report.

## 2. The Aura protocol

Every action uses the same shape. First the tool loads a community page, then it
reads the anti-CSRF token from a `Set-Cookie` header. Then it posts the action.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant P as Portal
    C->>P: GET /areaprivada/s/PAGE
    P-->>C: Set-Cookie __Host-ERIC...=eyJ... (aura.token)
    C->>P: POST /s/sfsites/aura?r=1&other.ROUTE=1
    Note over C: body: message + aura.context +<br/>aura.pageURI + aura.token
    P-->>C: JSON: actions[0].returnValue + context.fwuid
    C->>C: cache the token per page
    alt stale token ("/*ERROR*/" in the text)
        C->>P: GET the page again (new token)
        C->>P: POST the action again
    end
```

- The token is not decoded. The tool reads the `eyJ...` value from the
  `__Host-ERIC...` cookie and sends it back.
- The `fwuid` and the app version are refreshed from `context` in every
  response. This keeps the tool working when the portal changes them.

## 3. Login without a browser

`login` (and the auto login) use the portal login action. The login page is a
guest page, so its token is `null`.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant P as Portal
    C->>P: GET /areaprivada/s/login?language=es
    Note over C: new cookie jar (no session yet)
    C->>P: POST aura LightningLoginFormController.login
    Note over C: aura.token = null, params: username, password, startUrl
    P-->>C: guest response with aura:clientRedirect frontdoor.jsp...
    C->>P: GET frontdoor.jsp?sid=... (pre-session)
    P-->>C: page with redirect to /areaprivada/loginflow/...
    C->>P: GET /areaprivada/loginflow/...
    C->>P: GET /areaprivada/s/ (home)
    Note over C,P: the cookie jar now holds the sid cookie
    C-->>C: return sid
```

The tool follows the chain: frontdoor, login flow, landing page, home. The home
page then sets the `sid` cookie and the `aura.token` cookie.

## 4. The massive download

The full hourly history comes as one ZIP. The portal makes it in the background,
so the tool waits and then downloads it.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant P as Portal
    C->>P: getListCups (measure_list)
    P-->>C: lstIds, lstCups (records with rate), maxYears
    C->>P: getFiles
    P-->>C: lstFiles (the current files)
    C->>P: createZip (roleId, lstCupsIds, data, start, end, downloadType=1)
    P-->>C: "request processed" (async)
    loop every 3 s, up to --wait seconds (default 180)
        C->>P: getFiles
        P-->>C: lstFiles
    end
    Note over C: stop when a new fileid appears
    C->>P: GET /areaprivada/sfc/servlet.shepherd/version/download/FILEID
    P-->>C: ZIP bytes
    C->>P: deleteFile (transferId = Id)
    Note over C: the file is removed from the portal
```

- `downloadType=1` is the hourly data. The portal also has a quarter-hourly
  value (`2`).
- The range is the first contract start to the last contract end. The portal
  clips the ZIP per contract version. Each version becomes one CSV pair.
- The tool lists the files first, so it can detect the new file and delete it
  after the read.

## 5. Data pipeline

```mermaid
flowchart TD
    A["ZIP bytes"] --> B{"files ending in _Horario.csv<br/>(skip _CCH_CONS.csv)"}
    B --> C["rows: CUPS, Fecha, Hora, AE_kWh, REAL/ESTIMADO"]
    C --> D["clock_hour: row index to hour 0..23"]
    D --> E["hours: (day, hour) to (kWh, real)"]
    E --> F{"day is estimated with 0 kWh?"}
    F -- yes --> G["pending: no reading yet, do not count"]
    F -- no --> H["count the hour"]
    H --> I["aggregate: totals, periods,<br/>by year, month and hour, peaks"]
    I --> J["report (text) or JSON"]
```

- The tool reads one value per day, so a day with the change of the hour has 23
  or 25 rows. See section 7.
- A day with no reading yet comes as estimated with 0 kWh. The tool calls it
  `pending` and keeps it out of the totals. The recent zoom shows it.

## 6. The 2.0TD period

The portal does not send the tariff period with the ZIP. The tool works out the
period from the date and the hour. See
[TARIFF_2_0TD.md](TARIFF_2_0TD.md) for the law and the details.

```mermaid
flowchart TD
    S["day + hour"] --> W{"Saturday or Sunday?"}
    W -- yes --> P3a["P3"]
    W -- no --> H{"fixed national holiday?"}
    H -- yes --> P3b["P3"]
    H -- no --> P1{"10-14 or 18-22?"}
    P1 -- yes --> P1o["P1"]
    P1 -- no --> P2{"8-10, 14-18 or 22-24?"}
    P2 -- yes --> P2o["P2"]
    P2 -- no --> P3c["P3"]
```

## 7. The day status

The recent zoom and the reading map use one symbol per day.

```mermaid
flowchart TD
    D["rows of the day"] --> N{"any row?"}
    N -- no --> Dot[". no data"]
    N -- yes --> M{"real and estimated hours?"}
    M -- "both" --> Mixed["M mixed"]
    M -- "only real" --> Real["R real"]
    M -- "only estimated" --> V{"total kWh = 0?"}
    V -- yes --> Pending["P pending (no reading yet)"]
    V -- no --> Est["E estimated"]
```

## 8. Endpoints and actions

| alias | route | descriptor | page |
| ----- | ----- | ---------- | ---- |
| `login_info` | `WP_Monitor_CTRL.getLoginInfo` | `apex://WP_Monitor_CTRL/ACTION$getLoginInfo` | `/areaprivada/s/` |
| `list_cups` | `WP_Measure_v3_CTRL.getListCups` | `apex://WP_Measure_v3_CTRL/ACTION$getListCups` | `/areaprivada/s/wp-measurelist-v4` |
| `get_info` | `WP_Measure_v3_CTRL.getInfo` | `apex://WP_Measure_v3_CTRL/ACTION$getInfo` | `/areaprivada/s/wp-measure-detail-v4` |
| `measure_list` | `WP_Measure_v3_CTRL.getListCups` | `apex://WP_Measure_v3_CTRL/ACTION$getListCups` | `/areaprivada/s/wp-massivemeasuredownload-v3` |
| `create_zip` | `WP_Measure_v3_CTRL.createZip` | `apex://WP_Measure_v3_CTRL/ACTION$createZip` | `/areaprivada/s/wp-massivemeasuredownload-v3` |
| `get_files` | `WP_Download_Transfer_CTRL.getFiles` | `apex://WP_Download_Transfer_CTRL/ACTION$getFiles` | `/areaprivada/s/wp-massivemeasuredownload-v3` |
| `delete_file` | `WP_Download_Transfer_CTRL.deleteFile` | `apex://WP_Download_Transfer_CTRL/ACTION$deleteFile` | `/areaprivada/s/wp-massivemeasuredownload-v3` |
| `maximeter` | `WP_MaximeterHistogram_CTRL.getHistogramPoints` | `apex://WP_MaximeterHistogram_CTRL/ACTION$getHistogramPoints` | `/areaprivada/s/wp-maximeterhistogramdetail` |
| `atr_detail` | `WP_ContractATRDetail_CTRL.getATRDetail` | `apex://WP_ContractATRDetail_CTRL/ACTION$getATRDetail` | `/areaprivada/s/wp-atrcontractdetail` |

## 9. Request shape

The Aura body is form data with four fields. The tool builds them in
`Client.call`.

```
message = {
  "actions": [{
    "id": "1;a",
    "descriptor": "apex://WP_Measure_v3_CTRL/ACTION$getListCups",
    "callingDescriptor": "markup://c:WP_Massive_Measure_Download_v3",
    "params": { ... }
  }]
}

aura.context = {
  "mode": "PROD",
  "fwuid": "<current framework uid>",
  "app": "siteforce:communityApp",
  "loaded": { "APPLICATION@markup://siteforce:communityApp": "<version>" },
  "dn": [], "globals": {}, "uad": true
}

aura.pageURI = "/areaprivada/s/wp-massivemeasuredownload-v3"
aura.token   = "<value of the __Host-ERIC... cookie>"
```

The response holds one action. The tool reads `actions[0].returnValue` and
stops on a `state` that is not `SUCCESS`.

## 10. The API the tool does not use

`WP_Measure_v3_CTRL.getChartPointsByRange` gives the hourly curve, but only for
a short range (about 35 days per call). The full history needs many calls, so
the tool uses the one ZIP instead. See
[ASSUMPTIONS.md](ASSUMPTIONS.md).

## 11. Where each part lives

| part | in the code |
| ---- | ----------- |
| Aura body and POST | `Client.call`, `Client.token`, `Client._read_context` |
| Browserless login | `portal_login`, `login_context` |
| Session file | `Session` |
| Massive download | `list_measure_cups`, `create_zip`, `get_files`, `_download_measure_zip` |
| ZIP read | `read_zip_rows`, `clock_hour`, `zip_hours` |
| Period and day logic | `tariff_period`, `day_status`, `month_map`, `recent_ranges` |
| Aggregation and report | `aggregate`, `fetch_hours`, `collect_consumption`, `_build_report`, `_print_report` |
