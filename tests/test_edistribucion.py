"""Unit tests for the pure logic of the tool. No network and no session."""
import io
import zipfile
from datetime import date

import edistribucion as ed

HEADER = "CUPS;Fecha;Hora;AE_kWh;REAL/ESTIMADO"


def make_zip(files):
    """Build a zip in memory. files is a list of (name, text)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files:
            archive.writestr(name, text)
    return buffer.getvalue()


def csv_text(rows):
    return "\n".join([HEADER] + rows)


# ---------------------------------------------------------------- tariff_period
def test_tariff_period_weekday():
    friday = date(2026, 1, 2)
    assert ed.tariff_period(friday, 12) == "P1"
    assert ed.tariff_period(friday, 9) == "P2"
    assert ed.tariff_period(friday, 7) == "P3"
    assert ed.tariff_period(friday, 23) == "P2"


def test_tariff_period_weekend_and_holiday():
    assert ed.tariff_period(date(2026, 1, 3), 12) == "P3"   # Saturday
    assert ed.tariff_period(date(2026, 1, 4), 12) == "P3"   # Sunday
    assert ed.tariff_period(date(2026, 1, 1), 12) == "P3"   # fixed holiday


def test_tariff_period_easter_is_not_off_peak():
    assert ed.tariff_period(date(2024, 3, 29), 12) == "P1"  # Good Friday


def test_tariff_period_ceuta_melilla():
    friday = date(2026, 1, 2)
    zone = ed.ZONE_CEUTA_MELILLA
    assert ed.tariff_period(friday, 12, zone) == "P1"   # 11-15 is peak
    assert ed.tariff_period(friday, 20, zone) == "P1"   # 19-23 is peak
    assert ed.tariff_period(friday, 10, zone) == "P2"   # 8-11 is flat
    assert ed.tariff_period(friday, 15, zone) == "P2"   # 15-19 is flat
    assert ed.tariff_period(friday, 7, zone) == "P3"    # 0-8 is off-peak
    assert ed.tariff_period(date(2026, 1, 3), 12, zone) == "P3"   # Saturday
    assert ed.tariff_period(date(2026, 1, 1), 20, zone) == "P3"   # fixed holiday


def test_supply_zone_from_postal_code():
    assert ed.supply_zone({"postal_code": "51001"}) == ed.ZONE_CEUTA_MELILLA
    assert ed.supply_zone({"postal_code": "52002"}) == ed.ZONE_CEUTA_MELILLA
    assert ed.supply_zone({"postal_code": "28001"}) == ed.ZONE_PENINSULA
    assert ed.supply_zone({"postal_code": "08001"}) == ed.ZONE_PENINSULA


def test_supply_zone_from_city():
    assert ed.supply_zone({"city": "Ceuta"}) == ed.ZONE_CEUTA_MELILLA
    assert ed.supply_zone({"city": "Melilla"}) == ed.ZONE_CEUTA_MELILLA
    assert ed.supply_zone({"city": "Madrid"}) == ed.ZONE_PENINSULA
    assert ed.supply_zone({}) == ed.ZONE_PENINSULA


# ------------------------------------------------------------------- clock_hour
def test_clock_hour_normal_day():
    assert ed.clock_hour(24, 1) == 0
    assert ed.clock_hour(24, 24) == 23


def test_clock_hour_spring_forward():
    assert ed.clock_hour(23, 1) == 0
    assert ed.clock_hour(23, 2) == 1
    assert ed.clock_hour(23, 3) == 3     # hour 2 does not exist
    assert ed.clock_hour(23, 23) == 23


def test_clock_hour_fall_back():
    assert ed.clock_hour(25, 3) == 2
    assert ed.clock_hour(25, 4) == 2     # the hour 2 repeats
    assert ed.clock_hour(25, 5) == 3
    assert ed.clock_hour(25, 25) == 23


# -------------------------------------------------------------------- zip_hours
def test_zip_hours_reads_the_rows():
    payload = make_zip([("ES00_Horario.csv",
                         csv_text(["ES00;04/09/2026;1;0,085;R",
                                   "ES00;04/09/2026;2;0,106;E"]))])
    assert list(ed.zip_hours(payload)) == [
        (date(2026, 9, 4), 0, 0.085, True),
        (date(2026, 9, 4), 1, 0.106, False),
    ]


def test_zip_hours_skips_the_cch_cons_file():
    payload = make_zip([("ES00_Horario_CCH_CONS.csv",
                         csv_text(["ES00;04/09/2026;1;9,999;R"]))])
    assert list(ed.zip_hours(payload)) == []


def test_zip_hours_handles_a_day_of_23_rows():
    rows = ["ES00;29/03/2026;%d;1,000;R" % index for index in range(1, 24)]
    payload = make_zip([("ES00_Horario.csv", csv_text(rows))])
    hours = [hour for _, hour, _, _ in ed.zip_hours(payload)]
    assert hours == [0, 1, 3] + list(range(4, 24))


# ------------------------------------------------------------------- csv export
def test_write_hours_csv(tmp_path):
    payload = make_zip([("ES00_Horario.csv",
                         csv_text(["ES00;04/09/2026;1;0,085;R",
                                   "ES00;04/09/2026;2;0,106;E"]))])
    path = tmp_path / "curva.csv"
    ed.write_hours_csv(payload, "ES00", str(path))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "CUPS;Fecha;Hora;AE_kWh;AS_KWh;AE_AUTOCONS_kwh;REAL/ESTIMADO"
    assert lines[1] == "ES00;04/09/2026;1;0.085;0.0;0.0;R"
    assert lines[2] == "ES00;04/09/2026;2;0.106;0.0;0.0;E"


def test_export_path_for():
    assert ed.export_path_for(None, "ES00", True) is None
    assert ed.export_path_for("a.csv", "ES00", False) == "a.csv"
    assert ed.export_path_for("a.csv", "ES00", True) == "a-ES00.csv"


# ------------------------------------------------------------- max demand periods
def test_demand_point():
    point = ed.demand_point({"val": "5,024", "date": "20-02-2025 21:45"})
    assert point == {"kw": 5.024, "date": "20-02-2025", "hour": "21:45"}
    assert ed.demand_point(None) is None
    assert ed.demand_point({"val": ""}) is None


def test_max_demand_periods_picks_the_top_of_each_period():
    monthly = {
        "2025-01": {"P1": {"kw": 4.0, "date": "01-01-2025", "hour": "10:00"},
                    "P2": {"kw": 3.0, "date": "01-01-2025", "hour": "01:00"}},
        "2025-02": {"P1": {"kw": 4.5, "date": "02-02-2025", "hour": "11:00"},
                    "P2": {"kw": 2.5, "date": "03-02-2025", "hour": "02:00"}},
    }
    result = ed.max_demand_periods(monthly)
    assert result["2025"]["P1"]["kw"] == 4.5
    assert result["2025"]["P2"]["kw"] == 3.0


# ------------------------------------------------------------------- day_status
def test_day_status():
    assert ed.day_status(None) == "."
    assert ed.day_status({"real": 2, "estimated": 0, "kwh": 1.0}) == "R"
    assert ed.day_status({"real": 0, "estimated": 2, "kwh": 1.0}) == "E"
    assert ed.day_status({"real": 0, "estimated": 2, "kwh": 0.0}) == "P"
    assert ed.day_status({"real": 1, "estimated": 1, "kwh": 1.0}) == "M"


# -------------------------------------------------------------------- month_map
def test_month_map_mixed_and_pending():
    counts = {
        date(2026, 3, 1): {"real": 1, "estimated": 0, "kwh": 1.0},
        date(2026, 3, 2): {"real": 0, "estimated": 1, "kwh": 2.0},
        date(2026, 3, 3): {"real": 0, "estimated": 1, "kwh": 0.0},  # pending
    }
    assert ed.month_map(counts)[2026][2] == "M"


def test_month_map_ignores_pending():
    counts = {
        date(2026, 2, 1): {"real": 1, "estimated": 0, "kwh": 1.0},
        date(2026, 2, 2): {"real": 0, "estimated": 1, "kwh": 0.0},  # pending
    }
    assert ed.month_map(counts)[2026][1] == "R"


# ----------------------------------------------------------------- recent_ranges
def test_recent_ranges_marks_pending():
    counts = {
        date(2026, 1, 1): {"real": 1, "estimated": 0, "kwh": 1.0},
        date(2026, 1, 2): {"real": 1, "estimated": 0, "kwh": 1.0},
        date(2026, 1, 3): {"real": 0, "estimated": 1, "kwh": 0.0},  # pending
    }
    ranges = ed.recent_ranges(counts, date(2026, 1, 3), days=3)
    assert ranges == [
        (date(2026, 1, 1), date(2026, 1, 2), "R"),
        (date(2026, 1, 3), date(2026, 1, 3), "P"),
    ]


# -------------------------------------------------------------------- aggregate
def test_aggregate_sums_and_periods():
    hours = {
        (date(2026, 1, 1), 12): (1.0, True),    # holiday -> P3
        (date(2026, 1, 2), 12): (2.0, True),    # Friday -> P1
        (date(2026, 1, 3), 12): (3.0, False),   # Saturday -> P3, estimated
    }
    result = ed.aggregate(hours)
    assert result["real_kwh"] == 3.0
    assert result["estimated_kwh"] == 3.0
    assert result["real_hours"] == 2
    assert result["estimated_hours"] == 1
    assert result["periods_real_kwh"] == {"P1": 2.0, "P2": 0.0, "P3": 1.0}
    assert result["from"] == date(2026, 1, 1)
    assert result["to"] == date(2026, 1, 3)


def test_aggregate_ignores_pending_days():
    hours = {(date(2026, 1, 2), 0): (0.0, False)}   # estimated, no value
    result = ed.aggregate(hours)
    assert result["from"] is None
    assert result["real_kwh"] == 0.0
    assert result["estimated_kwh"] == 0.0


def test_aggregate_uses_the_zone():
    hours = {(date(2026, 1, 2), 14): (1.0, True)}   # Friday, 14:00-15:00
    assert ed.aggregate(hours)["periods_real_kwh"]["P2"] == 1.0
    assert ed.aggregate(hours, ed.ZONE_CEUTA_MELILLA)["periods_real_kwh"]["P1"] == 1.0


def test_aggregate_groups_by_weekday():
    hours = {(date(2026, 1, 2), 12): (2.0, True),   # Friday
             (date(2026, 1, 3), 12): (3.0, True)}   # Saturday
    weekdays = ed.aggregate(hours)["groups"]["weekday"]
    assert weekdays["Fri"]["real_kwh"] == 2.0
    assert weekdays["Sat"]["real_kwh"] == 3.0


def test_groups_list_keeps_the_given_order():
    groups = {
        "B": {"real_kwh": 1.0, "estimated_kwh": 0.0, "real_hours": 1, "estimated_hours": 0},
        "A": {"real_kwh": 2.0, "estimated_kwh": 0.0, "real_hours": 1, "estimated_hours": 0},
    }
    assert [row["key"] for row in ed._groups_list(groups)] == ["A", "B"]
    assert [row["key"] for row in ed._groups_list(groups, ["B", "A"])] == ["B", "A"]


# ---------------------------------------------------------------- measure_tariff
def test_measure_tariff():
    listing = {"lstCups": [{"Id": "c1", "rate": "2.0TD"},
                           {"Id": "c2", "rate": "3.0TD"}]}
    assert ed.measure_tariff(listing, [{"contract_id": "c1"}]) == "2.0TD"
    assert ed.measure_tariff(listing, [{"contract_id": "zz"}]) is None
