# e-distribucion client

This tool reads electricity data from the e-distribucion private area (Endesa
group) for your own account. It uses HTTP only. It uses only the Python
standard library.

It does three things:

1. Show the maximum demanded power per month.
2. Aggregate real consumption by hour, day, month, or year.
3. Find non-real (estimated) data and when it happens.

Warning: this tool is not official. It is not connected to e-distribucion or
Endesa. Use it only with your own account. The portal can change at any time.

## How it works

The portal is a Salesforce Experience Cloud site. The session is the `sid`
cookie. The tool also needs a short-lived anti-CSRF token. The server sends that
token in a cookie on the first request. The tool copies it and reuses it.

## Requirements

- Python 3.9 or newer.

## Authentication

Get the session with one of these commands. Full steps are in
[AUTHENTICATION.md](AUTHENTICATION.md).

- `login-backend` logs in with the user and the password. No browser. Add
  `--save` to store the credentials encrypted with the Windows DPAPI. Then the
  tool logs in again when the session expires.
- `import-cookies` reads a `cookies.txt` file.
- `save --sid` stores a value that you already have.

```bash
python edistribucion.py login-backend
```

## Commands

```bash
# List supplies. Shows the CUPS id and the contracted power.
python edistribucion.py cups

# Aggregate consumption by day (default). The CUPS is required.
python edistribucion.py consume --cups ES0031102226226018WR0F

# Aggregate by hour of the day, month, or year.
python edistribucion.py consume --cups ES0031102226226018WR0F --group hour
python edistribucion.py consume --cups ES0031102226226018WR0F --group month
python edistribucion.py consume --cups ES0031102226226018WR0F --group year

# Limit the period.
python edistribucion.py consume --cups ES0031102226226018WR0F --from 2024-01-16 --to 2026-09-12 --group month

# Maximum demanded power per month. The CUPS is required.
python edistribucion.py maxpower --cups ES0031102226226018WR0F

# JSON output.
python edistribucion.py consume --cups ES0031102226226018WR0F --group year --json
```

The options `--sid` and `--session` go before or after the command.

Example output:

```
CUPS: ES0031102226226018WR0F | contracted power: {'P1': 4.0} kW
Period: 2024-01-16 -> 2026-09-12 | group: month
Real: 5797.054 kWh (15911 h) | Estimated: 2743.035 kWh (7390 h)
Real periods: {'P1': 1890.896, 'P2': 1704.069, 'P3': 2202.089}
Estimated dates: 2024-03-02..2024-04-03, 2025-07-23..2025-12-09, ...
By month (real kWh | estimated kWh):
  2024-01        123.456 |      0.000
  ...
```

## Output fields

`consume` returns these keys:

| key | meaning |
| --- | ------- |
| `cups` | the CUPS used |
| `contracted_power_kw` | the contracted power of the supply |
| `real_kwh` | total measured consumption |
| `estimated_kwh` | total estimated consumption |
| `real_hours`, `estimated_hours` | count of measured and estimated hours |
| `periods_real_kwh` | measured total by `P1`, `P2`, `P3` |
| `estimated_days` | the dates with estimated data |
| `groups` | one entry per group, with real and estimated values |

`maxpower` returns these keys:

| key | meaning |
| --- | ------- |
| `requestedPower` | the contracted power in kW |
| `maxValue` | the single maximum, with the date and the time |
| `lstData` | one point per month, with the maxima per period |

## Security

The file `session.json` holds your live session cookie. The file
`credentials.json` holds the encrypted password. The `.gitignore` file excludes
both. Do not commit them. Do not share them.

The tool reads data from your own account only.

## License

MIT. See the `LICENSE` file.
