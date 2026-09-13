# Assumptions and limits

This file lists what the tool assumes. The tool was built and tested with one
real account. Some facts come from that account only. Other accounts can
differ. Read this list before you trust a number.

## 1. The tariff is 2.0TD (P1, P2, P3)

- In the test account, the CUPS has the tariff `2.0TD`, two contracted power
  periods (P1, P2), and three energy periods (P1, P2, P3).
- The tool puts every hour into three periods only.
- A `3.0TD` or `6.xTD` supply has six periods (P1 to P6) and another table of
  hours. The tool does not handle it. The zip still comes, but the period split
  is wrong.

## 2. The supply is in the Peninsula (or Illes Balears or Canarias)

- The tool uses the hours P1 10-14 and 18-22, P2 08-10, 14-18 and 22-24, P3
  00-08.
- Ceuta and Melilla have other hours. The tool does not use them.

## 3. The start of the data

- In the test account, the data starts on 2024-01-16, the start of the first
  contract version.
- This is a fact of that account. It is not a rule of the portal. The download
  page lets you pick a year from 2016.
- The tool asks for the range of the account: the start of the first contract
  to the end of the last contract. Data before the first contract version is
  not read.

## 4. Windows, for the saved password

- `login-backend --save` encrypts the password with the Windows DPAPI.
- That part works on Windows only. On Linux and macOS the tool runs, but
  `--save` does not work. Get the session another way.

## 5. Real or estimated

- The tool reads the `REAL/ESTIMADO` column of the CSV.
- A value that starts with `R` is real. Every other value is estimated.
- In the test account the values are `R` and `E` only.

## 6. The zip from the portal

- The tool asks for the hourly zip (`downloadType=1`). The portal also has a
  quarter-hourly zip.
- The tool waits up to 180 seconds for the zip. The portal makes the zip in the
  background. A large account can need more time.
- The tool reads files whose name ends in `_Horario.csv`, and skips the
  `_CCH_CONS.csv` files. If the portal changes the names, the read stops.
- The tool deletes the zip after the read. If the delete fails, the file stays
  in the portal.

## 7. The period calculation

- The tool marks a national holiday with a fixed date as off-peak (P3). The
  list has 9 dates. See [TARIFF_2_0TD.md](TARIFF_2_0TD.md).
- The tool assumes the change of the hour is on a Sunday and in the early
  morning, so the period of an hour does not change. This is true in Spain.
- The `Hora` column of the CSV is the position in the day. A day of the change
  of the hour has 23 or 25 rows, not 24.

## 8. The portal itself

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
