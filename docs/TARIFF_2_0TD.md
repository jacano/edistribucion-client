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

The hours depend on the zone. This table is the set of the Peninsula, the
Balearic Islands and the Canary Islands. Ceuta and Melilla use another set; see
the section "The zone" below.

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

## What the law says (BOE)

The Circular 3/2020 has the exact rule in Article 7, point 3. The original
text in Spanish says:

> Se consideran horas punta, llano y valle las siguientes: ... (Península,
> Illes Balears y Canarias) P1: 10 h-14 h y 18 h-22 h; P2: 8 h-10 h, 14 h-18 h
> y 22 h-24 h; P3: 0 h-8 h. Se consideran como horas del periodo 3 (valle)
> todas las horas de los sábados, domingos, el 6 de enero y los días festivos
> de ámbito nacional, definidos como tales en el calendario oficial del año
> correspondiente, con exclusión tanto de los festivos sustituibles como de
> los que no tienen fecha fija.

In Simple English: the peak, flat and off-peak hours are the ones in the table.
All the hours of a Saturday, a Sunday, 6 January and a national holiday are
off-peak. A national holiday counts only when it is in the official calendar
of that year. A holiday with a moveable date, or a holiday that can move to
another day, does not count.

This is the reason for the two rules in this tool:

- Easter has no fixed date, so Easter is not off-peak.
- 6 January is off-peak. The law writes it on its own, and it is also a fixed
  national holiday.

The law gives two sets of hours:

- Peninsula, Balearic Islands and Canary Islands: P1 10 h-14 h and 18 h-22 h.
- Ceuta and Melilla: P1 11 h-15 h and 19 h-23 h, P2 8 h-11 h, 15 h-19 h and
  23 h-24 h, P3 0 h-8 h.

This tool uses the set of hours of the zone of the supply. The next section
explains the zone.

The link to the law: <https://www.boe.es/buscar/act.php?id=BOE-A-2020-1066>
(Article 7, point 3).

## The zone

The period hours are not the same in the whole country. The law gives two sets:

- the Peninsula, the Balearic Islands and the Canary Islands,
- Ceuta and Melilla, whose hours are one hour later.

The tool works out the zone of each supply from the postal code:

- 51xxx is Ceuta,
- 52xxx is Melilla,
- any other code is the Peninsula, the Balearic Islands or the Canary Islands.

When the portal gives no postal code, the tool looks at the name of the city.
When there is no postal code and no city, the tool uses the hours of the
Peninsula. Add `--zone ceuta-melilla` to set the zone by hand.

## How the tool works out the period

The tool uses this function. The input is the date, the start hour of the hour
(a number from 0 to 23) and the zone.

```python
FIXED_HOLIDAYS = {(1, 1), (1, 6), (5, 1), (8, 15), (10, 12), (11, 1), (12, 6), (12, 8), (12, 25)}

ZONE_PEAK_HOURS = {
    "peninsula": ((10, 14), (18, 22)),
    "ceuta_melilla": ((11, 15), (19, 23)),
}
ZONE_FLAT_HOURS = {
    "peninsula": ((8, 10), (14, 18), (22, 24)),
    "ceuta_melilla": ((8, 11), (15, 19), (23, 24)),
}


def in_hour_windows(hour, windows):
    """Say if a clock hour is in one of the (start, end) windows."""
    return any(start <= hour < end for start, end in windows)


def tariff_period(day, hour, zone="peninsula"):
    """Return P1, P2 or P3 for a date, a clock hour and a 2.0TD zone."""
    if day.weekday() >= 5 or (day.month, day.day) in FIXED_HOLIDAYS:
        return "P3"
    if in_hour_windows(hour, ZONE_PEAK_HOURS[zone]):
        return "P1"
    if in_hour_windows(hour, ZONE_FLAT_HOURS[zone]):
        return "P2"
    return "P3"
```

`day.weekday()` is 5 for a Saturday and 6 for a Sunday. The weekend and a fixed
national holiday are P3 in every zone.

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

- Circular 3/2020 of the CNMC, Article 7, BOE-A-2020-1066:
  <https://www.boe.es/buscar/act.php?id=BOE-A-2020-1066>
- The 2.0TD calculation was checked against the free project
  [luzfija.es](https://github.com/almax-es/luzfija.es). Its period rules and its
  2026 grid fee and charge values helped to confirm the calculation of this
  tool.
