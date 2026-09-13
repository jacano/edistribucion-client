# e-distribucion client

This tool reads your electricity consumption from the e-distribucion private
area (Endesa group). It uses HTTP only. It runs in the terminal. It also works
as an MCP server for agents.

The tool does not use a browser. It uses only the Python standard library.

Warning: this tool is not official. It is not connected to e-distribucion or
Endesa. Use it only with your own account. The portal can change at any time.

## How it works

The portal is a Salesforce Experience Cloud site. The session is the `sid`
cookie.

The portal also needs an anti-CSRF token. The token name is `aura.token`. You
do not decode this token. The server sends the token in the `Set-Cookie`
header `__Host-ERIC_PROD...=eyJ...` each time a community page loads. The client
reads the token there and uses it again.

The flow has two steps. One GET request gets a token. Then the client sends
POST requests to `/s/sfsites/aura`.

## Requirements

- Python 3.9 or newer.

## Setup

1. Open `https://zonaprivada.edistribucion.com/areaprivada/s/` in your browser.
2. Log in.
3. Copy the `sid` cookie value. In DevTools, open Application, then Cookies,
   then `zonaprivada.edistribucion.com`, then `sid`.
4. Save the value:

```bash
python edistribucion.py save --sid "<sid cookie value>"
```

You can also put the value in the environment variable `EDIST_SID`.

## Commands

```bash
# Account and supplies. Shows the contracted power.
python edistribucion.py status

# Full supply list with all fields.
python edistribucion.py cups

# Billing periods, contracts, and the available date range.
python edistribucion.py periods

# Consumption for one month. Splits P1, P2 and P3. Marks real or estimated.
python edistribucion.py month --month 2026-09

# Consumption for a date range.
python edistribucion.py range --from 2026-09-01 --to 2026-09-30

# JSON output.
python edistribucion.py month --month 2026-09 --json
```

Example output:

```
Month 2026-09 (available 2026-09-04 -> 2026-09-12)
CUPS: ES0031...WR0F | contractId: a0ucj...
Range: 2026-09-04 -> 2026-09-12
Total: 61.153 kWh | peak demand: 14.683000000000002 kW
Periods (kWh): {'P3': 16.137, 'P2': 20.779, 'P1': 24.237}
Measured: 61.153 kWh (192 h) | Estimated: 0.0 kWh (24 h)

Daily detail:
  04/09/2026     2.336 kWh  MEASURED  {'P3': 0.781, 'P2': 0.783, 'P1': 0.772}
  ...
  12/09/2026     0.000 kWh  ESTIMATED {}
```

## Output fields

Each hour has these fields.

| field      | meaning                                  |
| ---------- | ---------------------------------------- |
| `kwh`      | consumption for the hour                 |
| `period`   | tariff period: `P1`, `P2`, or `P3`       |
| `method`   | `measured` (R) or `estimated` (E)        |
| `real`     | true when the value is a real measure    |
| `invoiced` | true when the value is already invoiced  |
| `valid`    | true when the hour is valid              |

The command `cups` shows the contracted power for each supply. Example:
`{"P1": 4.0}`.

## MCP server

The file `mcp_server.py` gives the client to an agent. It speaks MCP over
stdio. Configuration example:

```json
{
  "mcp": {
    "edistribucion": {
      "type": "local",
      "command": ["python", "/absolute/path/to/mcp_server.py"],
      "enabled": true
    }
  }
}
```

Tools:

| tool                      | description                                          |
| ------------------------- | ---------------------------------------------------- |
| `edist_status`            | account and supplies with contracted power           |
| `edist_supplies`          | full supply list                                     |
| `edist_periods`           | billing periods, contracts, and available range      |
| `edist_month_consumption` | month consumption by P1/P2/P3, real or estimated     |
| `edist_range_consumption` | consumption for a date range by P1/P2/P3             |

The server reads the session from `EDIST_SID` or from `sesion.json`.

## Session

The `sid` session ends after some time. If a command fails with an
authentication error, copy a new `sid` and run `save` again.

The client refreshes the `aura.token` on each call. The token lives about 60
seconds.

## Security

The file `sesion.json` holds your live session cookie. The `.gitignore` file
excludes this file. Do not commit it. Do not share it.

The client reads data from your own account only.

## License

MIT. See the `LICENSE` file.
