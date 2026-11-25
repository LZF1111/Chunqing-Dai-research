"""Generate a deterministic synthetic collocation file for smoke tests."""

from __future__ import annotations

import argparse
import csv
import math
import random
from datetime import date
from pathlib import Path


STATIONS = [
    ("CN_Beijing", 39.90, 116.40, "urban", 0.06),
    ("CN_Xianghe", 39.75, 116.96, "rural", 0.03),
    ("JP_Tokyo", 35.68, 139.69, "urban", 0.05),
    ("AU_Canberra", -35.28, 149.13, "rural", -0.01),
]
YEARS = (2018, 2019, 2020, 2021)
MONTHS = (2, 5, 8, 11)
FIELDNAMES = [
    "station_id",
    "timestamp",
    "latitude",
    "longitude",
    "aeronet_aod_500",
    "satellite_aod",
    "qa_value",
    "solar_zenith_deg",
    "view_zenith_deg",
    "relative_azimuth_deg",
    "surface_type",
    "air_temperature_k",
    "relative_humidity_pct",
    "boundary_layer_height_m",
]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/example_collocations.csv"),
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    randomizer = random.Random(20261124)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for station_index, (station, latitude, longitude, surface, surface_bias) in enumerate(
            STATIONS
        ):
            for year in YEARS:
                for month_index, month in enumerate(MONTHS):
                    seasonal = 0.07 * math.sin((month_index + 1) * math.pi / 2)
                    station_signal = 0.025 * station_index
                    noise = randomizer.uniform(-0.025, 0.025)
                    label = max(0.03, 0.12 + seasonal + station_signal + surface_bias + noise)
                    satellite_noise = randomizer.uniform(-0.045, 0.045)
                    satellite = max(0.01, label + surface_bias + satellite_noise)
                    day = 10 + month_index
                    timestamp = date(year, month, day).isoformat() + "T05:30:00Z"
                    writer.writerow(
                        {
                            "station_id": station,
                            "timestamp": timestamp,
                            "latitude": latitude,
                            "longitude": longitude,
                            "aeronet_aod_500": f"{label:.6f}",
                            "satellite_aod": f"{satellite:.6f}",
                            "qa_value": f"{0.92 + 0.01 * (month_index % 3):.3f}",
                            "solar_zenith_deg": f"{28 + 4 * month_index + station_index:.3f}",
                            "view_zenith_deg": f"{12 + 3 * station_index:.3f}",
                            "relative_azimuth_deg": f"{70 + 25 * month_index:.3f}",
                            "surface_type": surface,
                            "air_temperature_k": f"{278 + 8 * math.sin(month_index * math.pi / 2) + station_index:.3f}",
                            "relative_humidity_pct": f"{42 + 7 * ((month_index + station_index) % 4):.3f}",
                            "boundary_layer_height_m": f"{650 + 90 * month_index + 30 * station_index:.3f}",
                        }
                    )
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
