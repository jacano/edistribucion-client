# e-distribucion client

This tool reads electricity data from the e-distribucion private area (Endesa
group) for your own account. It uses HTTP only. It uses only the Python
standard library.

It gives one thing: a **full report**. The report uses all the data available
and covers every CUPS of the account, one after another. Each report contains:

- the tariff of the supply,
- the contracted power per period (P1, P2),
- the real and estimated consumption totals and the split by P1, P2, P3,
- the real and estimated consumption by year (with the P1, P2, P3 split),
  month, and hour,
- the maximum consumption in one hour per year,
- the maximum demanded power per year and per month,
- a warning when estimated data exists, with the dates.

Warning: this tool is not official. It is not connected to e-distribucion or
Endesa. Use it only with your own account. The portal can change at any time.

## Requirements

- Python 3.9 or newer.

## Install

From the folder of the project (the folder with `pyproject.toml`):

```bash
pipx install .        # recommended; or: pip install .
```

This gives the command `edistribucion`. Then run the report:

```bash
edistribucion           # the same as: edistribucion report
edistribucion report --json
```

Full steps (the first run, the file locations, update, uninstall) are in
[docs/INSTALL.md](docs/INSTALL.md).

## Authentication

Get the session with one of these commands. Full steps are in
[docs/AUTHENTICATION.md](docs/AUTHENTICATION.md).

- `login-backend` logs in with the user and the password. No browser. Add
  `--save` to store the credentials encrypted with the Windows DPAPI. Then the
  tool logs in again when the session expires.
- `import-cookies` reads a `cookies.txt` file.
- `save --sid` stores a value that you already have.

```bash
edistribucion login-backend --save      # installed tool
python edistribucion.py login-backend   # file, without installing
```

## Report

```bash
edistribucion report
```

The report uses all the data available. You do not set a period. The tool finds
the first and the last date by itself. With several CUPS, it prints one report
for each CUPS, one after another.

Option:

- `--json` gives raw JSON. With several CUPS, the JSON is a list.

Example output:

```
REPORT
CUPS: ES0031102226226018WR0F
Tariff: 2.0TD
Contracted power: {'P1': 4.0, 'P2': 4.0} kW
Period: 2024-01-16 -> 2026-09-14

CONSUMPTION
  Consumption        kWh            hours         P1         P2         P3
  Real          5797.068  15911 h (663 d)   1890.900   1704.064   2202.104
  Estimated     2742.983   7438 h (310 d)    810.040    657.056   1275.887
  By year (real | estimated kWh, real | estimated hours):
    2024    2007.797 |    595.522  |   6265 h (261 d) |   2158 h ( 90 d)
      P1   606.608 |  165.083
      P2   596.359 |  182.676
      P3   804.830 |  247.763
    2025    2613.067 |    912.146  |   5837 h (243 d) |   2922 h (122 d)
      ...
  By month (real | estimated kWh):
    2024-03      11.335 |    225.417
    ...

MAXIMUM PER YEAR
  Year   Peak hour  When                  Peak demand  When
  2024   3.330 kWh  15/12/2024 10 - 11 h     4.760 kW  28/10/2024
  2025   3.625 kWh  02/02/2025 21 - 22 h     5.024 kW  20/02/2025

WARNING: there are estimated consumptions.
  Estimated: 2742.983 kWh in 7438 hours (310 days)
  Estimated dates: 2024-03-02..2024-04-03, ...
```

The tool asks the portal for one zip with the hourly curves and reads it. Then
it deletes the zip from the portal. This is much faster than one call per month.
The period (P1, P2, P3) is worked out from the 2.0TD calendar. All the details
are in [docs/TARIFF_2_0TD.md](docs/TARIFF_2_0TD.md).

The report shows the tariff. When the tariff is not 2.0TD, the tool stops with
an error and gives no report data. The full list of assumptions and limits is
in [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md).

## Security

The file `session.json` holds your live session cookie. The file
`credentials.json` holds the encrypted password. The `.gitignore` file excludes
both. Do not commit them. Do not share them.

The tool reads data from your own account only.

## License

MIT. See the `LICENSE` file.
