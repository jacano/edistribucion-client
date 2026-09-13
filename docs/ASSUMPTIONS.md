# Assumptions and limits

This file lists what the tool assumes. The tool was built and tested with one
real account. Some facts come from that account only. Other accounts can
differ. Read this list before you trust a number.

## 1. The tariff is 2.0TD (P1, P2, P3)

- The report shows the tariff of the supply.
- The tool puts every hour into three periods only (P1, P2, P3).
- When the tariff is not `2.0TD`, the tool stops with an error and gives no
  report data.
- A `3.0TD` or `6.xTD` supply has six periods (P1 to P6) and another table of
  hours. The tool does not handle it.

## 2. The supply is in the Peninsula (or Illes Balears or Canarias)

- The tool uses the hours P1 10-14 and 18-22, P2 08-10, 14-18 and 22-24, P3
  00-08.
- Ceuta and Melilla have other hours, so the period split can be wrong for a
  supply there.

## 3. Windows, for the saved password

- `login-backend --save` encrypts the password with the Windows DPAPI.
- That part works on Windows only. On Linux and macOS the tool runs, but
  `--save` does not work. Get the session another way.

## 4. Real or estimated

- The tool reads the `REAL/ESTIMADO` column of the CSV.
- A value that starts with `R` is real. Every other value is estimated.
- In the test account the values are `R` and `E` only.
- The last one or two days come as estimated with 0 kWh, because the portal has
  no reading for them yet. The tool marks these days as `pending`, not as
  estimated consumption.
- The portal publishes the real reading of a day with a small delay. In the
  test account the last real day was two days before today.

## 5. The zip from the portal

- The tool gets the hourly history from the massive download, as one zip. It
  does not use the per-range API `WP_Measure_v3_CTRL.getChartPointsByRange`.
- That per-range API gives the hourly curve, but only for a short range (about
  35 days in the test account). The full history needs one call for each range
  (33 calls in the test account). That does not scale.
- Both methods give the same result. In the test the real total and the split
  by P1, P2 and P3 were the same, with a difference of about 0.01 kWh. That
  difference is the rounding of the CSV (3 decimals).
- The tool asks for the hourly zip (`downloadType=1`). The portal also has a
  quarter-hourly zip.
- The tool waits up to 180 seconds for the zip. The portal makes the zip in the
  background. A large account can need more time.
- The tool reads files whose name ends in `_Horario.csv`, and skips the
  `_CCH_CONS.csv` files. If the portal changes the names, the read stops.
- The tool deletes the zip after the read. If the delete fails, the file stays
  in the portal.

## 6. The period calculation

- The tool marks a national holiday with a fixed date as off-peak (P3). The
  list has 9 dates. See [TARIFF_2_0TD.md](TARIFF_2_0TD.md).
- The tool assumes the change of the hour is on a Sunday and in the early
  morning, so the period of an hour does not change. This is true in Spain.
- The `Hora` column of the CSV is the position in the day. A day of the change
  of the hour has 23 or 25 rows, not 24.

## 7. The portal itself

- The action names, the Aura `fwuid`, and the app version are fixed values in
  the code. They came from the portal at one time. The portal can change them.
- The tool reads the token from the `Set-Cookie` header `__Host-ERIC...`. The
  portal can change the name.
- The tool reads the contracted power from the ATR detail page, from the name
  `Potencia contratada`.

## What to do when an assumption is false

- The tool stops, or a number is wrong.
- Check the tariff first. A supply that is not 2.0TD needs the six-period
  table.
