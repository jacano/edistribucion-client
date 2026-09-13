# e-distribucion client

This tool reads electricity data from the e-distribucion private area (Endesa
group) for your own account. It uses HTTP only. It uses only the Python
standard library.

It gives one thing: a **full report**. The report uses all the data available
and covers every CUPS of the account, one after another. Each report contains:

- the contracted power per period (P1, P2),
- the real consumption total and the split by P1, P2, P3,
- the real consumption by year, month, and hour,
- the maximum consumption in one hour per year,
- the maximum demanded power per year and per month,
- a warning when estimated data exists, with the dates.

Warning: this tool is not official. It is not connected to e-distribucion or
Endesa. Use it only with your own account. The portal can change at any time.

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

## Report

```bash
python edistribucion.py report
```

The report uses all the data available. You do not set a period. The tool finds
the first and the last date by itself. With several CUPS, it prints one report
for each CUPS, one after another.

Option:

- `--json` gives raw JSON. With several CUPS, the JSON is a list.

Example output:

```
REPORT
CUPS: ES0031102226226018WR0F | cups_id: a0r2400000GIpw1AAD
Contracted power: {'P1': 4.0, 'P2': 4.0} kW
Period: 2024-01-16 -> 2026-09-12

REAL CONSUMPTION
  Total: 5797.054 kWh in 15911 hours
  Periods: {'P1': 1890.896, 'P2': 1704.069, 'P3': 2202.089}
  By year (real | estimated kWh):
    2024    2007.799 |    595.531
    ...
  By month (real | estimated kWh):
    2024-03      11.335 |    225.435
    ...

MAX HOURLY CONSUMPTION
  2025  3.625 kWh  (02/02/2025 21 - 22 h)

MAX DEMANDED POWER (monthly, from the portal)
  2025  5.024 kW  (20-02-2025)

WARNING: there are estimated consumptions.
  Estimated: 2743.035 kWh in 7390 hours
  Estimated dates: 2024-03-02..2024-04-03, ...
```

The tool asks the portal for one zip with the hourly curves and reads it. This
is much faster than one call per month. The period (P1, P2, P3) is worked out
from the 2.0TD calendar. All the details are in
[TARIFF_2_0TD.md](TARIFF_2_0TD.md). The portal has no data before 2024-01-16.

## Security

The file `session.json` holds your live session cookie. The file
`credentials.json` holds the encrypted password. The `.gitignore` file excludes
both. Do not commit them. Do not share them.

The tool reads data from your own account only.

## License

MIT. See the `LICENSE` file.
