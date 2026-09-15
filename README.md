# e-distribucion client

This tool reads electricity data from the e-distribucion private area (Endesa
group) for your own account. It uses HTTP only. It uses only the Python
standard library.

It gives one thing: a **full report**. The report uses all the data available
and covers every CUPS of the account, one after another. Each report contains:

- the tariff of the supply,
- the zone of the supply (the Peninsula, Baleares and Canarias hours, or the
  Ceuta and Melilla hours),
- the contracted power per period (P1, P2),
- the real and estimated consumption totals and the split by P1, P2, P3,
- the real and estimated consumption by year (with the P1, P2, P3 split),
  month, hour, and weekday,
- the maximum consumption in one hour per year, from the real values,
- the maximum demanded power per year, with the split by power period (P1 and
  P2) and the months above the contracted power (the full list per month is in
  the JSON),
- the longest period in a row with real data only, with its totals by P1, P2,
  P3 and the number of days, ready for a comparator,
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

- `login` logs in with the user and the password. No browser. Add `--save` to
  keep the password in the credential store of the system (DPAPI on Windows,
  Keychain on macOS, libsecret on Linux). Then the tool logs in again when the
  session expires. Without `--save`, it asks before saving.
- `import-cookies` reads a `cookies.txt` file. Use the browser extension "Get
  cookies.txt LOCALLY" (Chrome and Firefox); the links are in the guide.
- `set-session --sid` stores a session value that you already have.

```bash
edistribucion login --save      # installed tool
python edistribucion.py login   # file, without installing
```

## Report

```bash
edistribucion report
```

The report uses all the data available. You do not set a period. With several
CUPS, the tool first prints a summary table (one line per CUPS with its totals),
then one full report for each CUPS under a banner `CUPS i of N`.

Option:

- `--json` gives raw JSON. With several CUPS, the JSON is a list.

The tool has these options. They work with every command:

- `--wait SECONDS` sets the time to wait for the portal zip (default 180).
- `--keep-artifacts` keeps the zip file and the portal notification (see below).
- `--quiet` hides the progress lines.
- `--verbose` shows more detail, such as the token refresh.
- `--zone ZONE` sets the 2.0TD zone: `peninsula` or `ceuta-melilla`. Without it,
  the tool reads the postal code of the supply (51xxx is Ceuta, 52xxx is
  Melilla).
- `--export-csv FILE` writes the hourly curves to a CSV file. The header is the
  one of the portal (`CUPS;Fecha;Hora;AE_kWh;AS_KWh;AE_AUTOCONS_kwh;REAL/ESTIMADO`),
  so the file works with the CSV import of the electricity comparators. With
  several CUPS, the tool adds the CUPS to the name of the file.
- `--trace [DIR]` writes every request, every response and every downloaded file
  to a folder, one folder for each run. The default folder is `traces` in the
  state folder. See "Troubleshooting" below.

Add them before or after the command.

### The zip file and the notification

For each CUPS, the tool asks the portal for one zip with the massive curves.
The portal makes the zip in the background and also creates a notification
("Descarga de curvas de consumo").

By default, the tool deletes both after the read:

- the zip file, from the download list,
- the notification, from the notification list.

Add `--keep-artifacts` to keep both on the portal. Use it to read the zip by hand, or to
keep the portal history.

The portal can disable the notification for a role. The setting is "No deseo
recibir más notificaciones para este rol" (I do not want more notifications for
this role). When it is on, the portal makes no notification, and there is
nothing to delete.

### Troubleshooting

Add `--trace` to keep everything the tool sends and receives. The tool writes
one folder for each run, with this content:

- `log.txt`: the progress lines,
- `NNN-<action>-request.txt`: the request: the method, the URL, the headers and
  the body,
- `NNN-<action>-response.txt`: the status, the headers and the raw response,
- `NNN-download-<id>.zip`: the zip of the hourly curves.

Use it when a run fails, and keep the folder. The tool masks the user and the
password of a `login` run. The session cookie and the token stay as they are.
Keep the folder private. Do not put it in a public place.

Example output:

```
REPORT
CUPS: ES0031100000000000NN0N
Tariff: 2.0TD
Zone: Peninsula, Baleares and Canarias
Contracted power: P1 4.0 kW, P2 4.0 kW
Period: 2024-01-16 -> 2026-09-12

CONSUMPTION
  Consumption        kWh            hours     P1 kWh     P2 kWh     P3 kWh
  Real          5797.068  15911 h (663 d)   1890.900   1704.064   2202.104
  Estimated     2742.983   7390 h (308 d)    810.040    657.056   1275.887
  Total         8540.051  23301 h (971 d)   2700.940   2361.120   3477.991
  By year
    Year       real kWh    est. kWh   total kWh   real hours     est. hours
    2024       2007.797     595.522    2603.319   6265 h (261 d) 2158 h (90 d)
    2025       2613.067     912.146    3525.213   5837 h (243 d) 2922 h (122 d)
    2026       1176.204    1235.315    2411.519   3809 h (159 d) 2310 h (96 d)
  By year period (kWh)
    Year        P1 real     P1 est     P2 real     P2 est     P3 real     P3 est
    2024        606.608    165.083     596.359    182.676     804.830    247.763
    ...
    2026        425.850    392.497     342.300    324.706     408.054    518.112
  By month
    Month       real kWh    est. kWh   total kWh
    2024-03       11.335     225.417     236.752
    ...
  By hour of day
    Hour        real kWh    est. kWh   total kWh
    00           215.885     117.451     333.336
    ...
  By weekday
    Day         real kWh    est. kWh   total kWh
    Mon          891.332     391.535    1282.867
    ...

REAL STREAK (the longest period with real data only)
  Period: 2025-01-21 -> 2025-07-22 (183 days)
        P1 kWh      P2 kWh      P3 kWh   total kWh
       545.882     482.184     692.202    1720.268

MAXIMUM PER YEAR
  Peak hour: the most energy in one hour (kWh), from the real values.
  Year   Peak hour  When
  2024   3.330 kWh  15/12/2024 10 - 11 h
  2025   3.625 kWh  02/02/2025 21 - 22 h

MAXIMUM DEMANDED POWER (kW, 15 minute measure)
  The contract has one power for P1 and one power for P2.
  Year   P1         When                    P2         When
  2024   4.756 kW   28-10-2024 22:15        3.936 kW   08-09-2024 21:15
  2025   5.024 kW   20-02-2025 21:45        4.936 kW   23-03-2025 12:15
  The portal does not return every month.
  No month above the contracted power.

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
the 2.0TD calendar and the zone of the supply. All the details are in
[docs/TARIFF_2_0TD.md](docs/TARIFF_2_0TD.md).

The Aura protocol, the browserless login and the download flow have diagrams in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

The tool does not use the per-range API
`WP_Measure_v3_CTRL.getChartPointsByRange`. It gives the curve, but only about
35 days per call, so the full history needs many calls and does not scale. The
zip needs one request, and the result is the same. See
[docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md).

The report shows the tariff. When the tariff is not 2.0TD, the tool stops with
an error and gives no report data. The full list of assumptions and limits is
in [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md).

## Development

```bash
pip install -e ".[dev]"
ruff check .      # lint
pytest            # tests (no network)
```

The tests cover the pure logic only: the 2.0TD periods, the zip read, the day
status, the reading map and the aggregation. They need no session and no
network.

## Acknowledgements

- The 2.0TD calculation was checked against
  [luzfija.es](https://github.com/almax-es/luzfija.es). The period rules of that
  project, and its 2026 grid fee and charge values, helped to confirm the
  calculation of this tool.

## Security

The file `session.json` holds your live session cookie. The file
`credentials.json` holds your saved credentials: the username, and on Windows
the encrypted password. On macOS and Linux the password stays in the Keychain
or in libsecret, and the file holds the username only. The `.gitignore` file
excludes both files. Do not commit them. Do not share them.

The tool reads data from your own account only.

## License

MIT. See the `LICENSE` file.
