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
- the maximum demanded power per year (the full list per month is in the JSON),
- a zoom of the last 3 months (the last reading and its delay) and a monthly
  reading map, so you see what is real, estimated or pending.

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
  `--save` to keep the password in the credential store of the system (DPAPI on
  Windows, Keychain on macOS, libsecret on Linux). Then the tool logs in again
  when the session expires.
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

The report uses all the data available. You do not set a period. With several
CUPS, it prints one report for each CUPS, one after another.

Option:

- `--json` gives raw JSON. With several CUPS, the JSON is a list.

Example output:

```
REPORT
CUPS: ES0031100000000000NN0N
Tariff: 2.0TD
Contracted power: P1 4.0 kW, P2 4.0 kW
Period: 2024-01-16 -> 2026-09-14

CONSUMPTION
  Consumption        kWh            hours         P1         P2         P3
  Real          5797.068  15911 h (663 d)   1890.900   1704.064   2202.104
  Estimated     2742.983   7438 h (310 d)    810.040    657.056   1275.887
  Total         8540.051  23349 h (973 d)   2700.940   2361.120   3477.991
  By year
    Year       real kWh    est. kWh   total kWh       real hours     est. hours
    2024       2007.797     595.522    2603.319   6265 h (261 d)  2158 h (90 d)
    2025       2613.067     912.146    3525.213   5837 h (243 d) 2922 h (122 d)
    Total      5797.068    2742.983    8540.051   15911 h (663 d) 7438 h (310 d)
  By year period
    Year        P1 real     P1 est     P2 real     P2 est     P3 real     P3 est
    2024        606.608    165.083     596.359    182.676     804.830    247.763
    ...
    Total      1890.900    810.040    1704.064    657.056    2202.104   1275.887
  By month
    Month       real kWh    est. kWh   total kWh
    2024-03       11.335     225.417     236.752
    ...
  By hour of day
    Hour        real kWh    est. kWh   total kWh
    00           215.885     117.451     333.336
    ...

MAXIMUM PER YEAR
  Year   Peak hour  When                  Peak demand  When
  2024   3.330 kWh  15/12/2024 10 - 11 h     4.760 kW  28/10/2024 22:15
  2025   3.625 kWh  02/02/2025 21 - 22 h     5.024 kW  20/02/2025 21:45

RECENT (last 3 months)
  Today:        2026-09-14
  Last reading: 2026-09-12 (real, 2 days old)
  Ranges:
    2026-06-17..2026-07-22   real
    2026-07-23               mixed
    2026-07-24               estimated
    2026-07-25..2026-09-12   real
    2026-09-13..2026-09-14   pending (no reading yet)

READING MAP (R real, E estimated, M mixed, . no data)
      Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec
2024   R   R   M   M   M   E   M   M   R   R   R   R
2025   M   R   R   R   R   R   M   E   E   M   M   M
2026   M   E   M   M   M   M   M   R   R   .   .   .
```

The tool asks the portal for one zip with the hourly curves and reads it. Then
it deletes the zip from the portal. The period (P1, P2, P3) is worked out from
the 2.0TD calendar. All the details are in
[docs/TARIFF_2_0TD.md](docs/TARIFF_2_0TD.md).

The tool does not use the per-range API
`WP_Measure_v3_CTRL.getChartPointsByRange`. It gives the curve, but only about
35 days per call, so the full history needs many calls and does not scale. The
zip needs one request, and the result is the same. See
[docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md).

The report shows the tariff. When the tariff is not 2.0TD, the tool stops with
an error and gives no report data. The full list of assumptions and limits is
in [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md).

## Security

The file `session.json` holds your live session cookie. The file
`credentials.json` holds your saved credentials: the username, and on Windows
the encrypted password. The `.gitignore` file excludes both. Do not commit
them. Do not share them.

The tool reads data from your own account only.

## License

MIT. See the `LICENSE` file.
