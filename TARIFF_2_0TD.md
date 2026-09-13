# The 2.0TD tariff and the period calculation

This file explains the 2.0TD tariff and how this tool works out the period
(P1, P2, P3) of each hour. The tool uses this calculation for the `report`
command.

## What the 2.0TD tariff is

- The 2.0TD is the electricity tariff for a supply at low voltage with a
  contracted power up to 15 kW. Most homes use it.
- The law is the Circular 3/2020 of the CNMC (BOE-A-2020-1066).
- The year has three periods. Each period has a different price for the grid
  fee. The names are peak (punta), flat (llano), and off-peak (valle).
- The periods change with the time of day and the type of day.

## The three periods

| Period | Name | Hours (Monday to Friday) |
| ------ | ---- | ------------------------ |
| P1 | Peak (punta) | 10:00-14:00 and 18:00-22:00 |
| P2 | Flat (llano) | 08:00-10:00, 14:00-18:00, and 22:00-00:00 |
| P3 | Off-peak (valle) | 00:00-08:00 |

P1 is the most expensive. P3 is the cheapest.

## Working days (Monday to Friday)

- Use the table above.
- The period of an hour is the period of the hour start. Hour 10:00-11:00 is
  P1. Hour 09:00-10:00 is P2. Hour 07:00-08:00 is P3.

## Saturdays, Sundays and national holidays

- On a Saturday or a Sunday, all the 24 hours are P3.
- On a national holiday with a fixed date, all the 24 hours are P3.
- The peak and flat periods do not exist on those days.

## The fixed national holidays

Only 9 days are off-peak. They repeat every year on the same date:

| Date | Day |
| ---- | --- |
| 1 January | New Year |
| 6 January | Epiphany |
| 1 May | Labour Day |
| 15 August | Assumption |
| 12 October | National Day |
| 1 November | All Saints |
| 6 December | Constitution Day |
| 8 December | Immaculate Conception |
| 25 December | Christmas |

The tool checks the month and the day, so it works for every year.

## Days that are NOT off-peak

- A regional holiday (for example, the day of the region) is not off-peak.
- A local holiday (a town fair) is not off-peak.
- Easter (Maundy Thursday and Good Friday) is not off-peak.
- A fixed national holiday that falls on a Sunday, and moves to the next
  Monday, makes that Monday a regional holiday. That Monday is not off-peak.

Easter is the common error. Easter has no fixed date, so it does not count as
off-peak. The whole of Easter week uses the normal periods of a working day.

## How the tool works out the period

The tool uses this function. The input is the date and the start hour of the
hour. The start hour is a number from 0 to 23.

```python
FIXED_HOLIDAYS = {(1, 1), (1, 6), (5, 1), (8, 15), (10, 12), (11, 1), (12, 6), (12, 8), (12, 25)}


def tariff_period(day, hour):
    """Return P1, P2 or P3 for a date and a clock hour, on the 2.0TD tariff."""
    if day.weekday() >= 5 or (day.month, day.day) in FIXED_HOLIDAYS:
        return "P3"
    if 10 <= hour < 14 or 18 <= hour < 22:
        return "P1"
    if 8 <= hour < 10 or 14 <= hour < 18 or 22 <= hour < 24:
        return "P2"
    return "P3"
```

`day.weekday()` is 5 for a Saturday and 6 for a Sunday.

## How the period was verified

The portal sends the period of each hour in the data of the old method. The
tool compared its own period with the period of the portal.

- The test compared 23,322 hours, from 2024-01-16 to 2026-09-14.
- The real/estimated flag: 0 differences.
- The consumption in kWh: the same in every hour.
- The period: the same in every hour, when the tool used the 9 fixed holidays.
  Before that, the tool also marked Easter as off-peak, and the portal did not.

The small result of the test:

| Period | From the portal | From this calculation |
| ------ | --------------- | --------------------- |
| P1 | 1890.896 kWh | 1890.900 kWh |
| P2 | 1704.069 kWh | 1704.064 kWh |
| P3 | 2202.085 kWh | 2202.104 kWh |

The two columns are almost the same. The small difference comes from the last
days, which the portal did not have yet.

## Change of the hour (DST)

- The change of the hour is on a Sunday. All the hours of a Sunday are P3.
- So the change of the hour never changes the period of an hour.
- In the zip file, the `Hora` column counts the rows of the day. A day with
  the change of the hour has 23 or 25 rows, not 24. The tool reads the rows in
  order, so the totals stay correct.

## Where the data comes from

- The tool asks the portal for one zip with the hourly curves. The name of the
  action is `WP_Measure_v3_CTRL.createZip`.
- Each row of the zip has this form:
  `CUPS;Fecha;Hora;AE_kWh;AS_KWh;AE_AUTOCONS_kWh;REAL/ESTIMADO`.
- `AE_kWh` is the energy used in the hour. `REAL/ESTIMADO` is `R` for a real
  value and `E` for an estimated value.
- The tool adds the `AE_kWh` of each hour and puts it in the period of that
  hour.

## Sources

- Preciluz, "Dias festivos y precio de la luz":
  <https://preciluz.com/dias-festivos-luz/>
- Plenitude, "Tarifa 2.0TD de Luz":
  <https://eniplenitude.es/blog/actualidad/nuevo-recibo-de-la-luz/>
- Circular 3/2020 of the CNMC, BOE-A-2020-1066.
