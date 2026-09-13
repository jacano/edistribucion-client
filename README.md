# e-distribucion client

This tool reads your electricity consumption from the e-distribucion private
area (Endesa group). It uses HTTP only. It runs in the terminal. It is friendly
for LLM agents. See [AGENTS.md](AGENTS.md).

The client uses only the Python standard library.

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

## Authentication

Start with the `login` command. It opens the e-distribucion login page. Then it
offers two ways to return the session to the tool:

1. Paste a line from DevTools (the `Cookie` header, or "Copy as cURL").
2. Import a `cookies.txt` file.

You can also pass the session directly with `--sid`.

Full steps are in [AUTHENTICATION.md](AUTHENTICATION.md).

```bash
python edistribucion.py login
```

## Console method

Use this method when the session is hard to copy. The tool does not need the
session. The page runs the query and copies the result.

1. Log in to the portal.
2. Run `python edistribucion.py js`. Copy the printed code.
3. Open DevTools and select the Console tab.
4. Paste the code. Press Enter.
5. Answer the prompt. The result goes to your clipboard.
6. Run `python edistribucion.py paste`. Paste the result. Press Enter, then
   `Ctrl+Z`, then Enter.

The command prints the formatted result.

Note: a Console snippet cannot read the `sid` cookie, because it is HttpOnly.
So this method returns the data, not the session.

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

The options `--sid` and `--session` go before or after the command.

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

## Session

The `sid` session ends after some time. If a command fails with an
authentication error, get a new `sid`. See
[AUTHENTICATION.md](AUTHENTICATION.md).

The client refreshes the `aura.token` on each call. The token lives about 60
seconds.

## Security

The file `sesion.json` holds your live session cookie. The `.gitignore` file
excludes this file. Do not commit it. Do not share it.

The client reads data from your own account only.

## License

MIT. See the `LICENSE` file.
