"""
Visualize anomaly A (Going Dark) events on an interactive world map.

Each event shows the last known position before AIS blackout (origin)
and the first position after reappearance (destination), connected by a line.

Hovering on any marker or line shows MMSI, gap duration, distance, and coordinates.
Layers can be toggled via the built-in layer control.

Usage:
    python visualization/going_dark_map.py
    python visualization/going_dark_map.py --input path/to/csv --output path/to/html
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import folium

# ── Default paths ────────────────────────────────────────────────────────────
DEFAULT_INPUT_CSV = Path("data/output/top_going_dark_vessel_map.csv")
DEFAULT_OUTPUT_HTML = Path("visualization/output/going_dark_map.html")

# ── Colors ───────────────────────────────────────────────────────────────────
ORIGIN_COLOR = "#1f77b4"      # steel blue  — last known position
DEST_COLOR = "#d62728"        # crimson     — reappearance
LINE_COLOR = "#ff7f0e"        # orange      — blackout path

MARKER_RADIUS = 7
LINE_WEIGHT = 2


def build_going_dark_map(input_csv: Path, output_html: Path) -> None:
    """Build an interactive map for anomaly A (Going Dark events)."""

    if not input_csv.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")

    events = []
    with input_csv.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            events.append({
                "mmsi": int(row["mmsi"]),
                "event_index": int(row["event_index"]),
                "lat_origin": float(row["lat_origin"]),
                "lon_origin": float(row["lon_origin"]),
                "lat_destination": float(row["lat_destination"]),
                "lon_destination": float(row["lon_destination"]),
                "gap_hours": float(row["gap_hours"]),
                "distance_km": float(row["distance_km"]),
            })

    if not events:
        print("No going dark events found — skipping.")
        return

    # Single-pass bounding box
    south = north = events[0]["lat_origin"]
    west = east = events[0]["lon_origin"]
    for e in events:
        for lat_key, lon_key in (("lat_origin", "lon_origin"), ("lat_destination", "lon_destination")):
            lat, lon = e[lat_key], e[lon_key]
            if lat < south: south = lat
            if lat > north: north = lat
            if lon < west: west = lon
            if lon > east: east = lon

    pad_lat = max(0.005, (north - south) * 0.15)
    pad_lon = max(0.005, (east - west) * 0.15)

    fmap = folium.Map(
        location=[(south + north) / 2, (west + east) / 2],
        zoom_start=6,
        tiles="CartoDB positron",
        control_scale=True,
    )

    # Feature groups for layer control
    fg_origins = folium.FeatureGroup(name="Last known positions")
    fg_dests = folium.FeatureGroup(name="Reappearance positions")
    fg_lines = folium.FeatureGroup(name="Blackout paths")

    for event in events:
        origin = (event["lat_origin"], event["lon_origin"])
        dest = (event["lat_destination"], event["lon_destination"])
        idx = event["event_index"]
        gap = event["gap_hours"]
        dist = event["distance_km"]
        mmsi = event["mmsi"]

        origin_tip = (
            f"<b>Last known position</b> | Event {idx}<br>"
            f"MMSI: {mmsi}<br>"
            f"({origin[0]:.5f}, {origin[1]:.5f})<br>"
            f"Gap: {gap:.1f} h | {dist:.1f} km"
        )
        dest_tip = (
            f"<b>Reappearance</b> | Event {idx}<br>"
            f"MMSI: {mmsi}<br>"
            f"({dest[0]:.5f}, {dest[1]:.5f})<br>"
            f"Gap: {gap:.1f} h | {dist:.1f} km"
        )
        line_tip = (
            f"<b>Going Dark — Event {idx}</b><br>"
            f"MMSI: {mmsi}<br>"
            f"Gap: {gap:.1f} h | {dist:.1f} km"
        )

        # Origin marker
        folium.CircleMarker(
            location=origin,
            radius=MARKER_RADIUS,
            color="black",
            fill=True,
            fill_color=ORIGIN_COLOR,
            fill_opacity=0.9,
            weight=1,
            tooltip=origin_tip,
        ).add_to(fg_origins)

        # Destination marker
        folium.CircleMarker(
            location=dest,
            radius=MARKER_RADIUS,
            color="black",
            fill=True,
            fill_color=DEST_COLOR,
            fill_opacity=0.9,
            weight=1,
            tooltip=dest_tip,
        ).add_to(fg_dests)

        # Connecting line
        folium.PolyLine(
            locations=[origin, dest],
            color=LINE_COLOR,
            weight=LINE_WEIGHT,
            opacity=0.7,
            tooltip=line_tip,
        ).add_to(fg_lines)

    fg_lines.add_to(fmap)
    fg_origins.add_to(fmap)
    fg_dests.add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)

    # Fit bounds
    fmap.fit_bounds(
        [[south - pad_lat, west - pad_lon], [north + pad_lat, east + pad_lon]],
    )

    # Legend
    legend_html = f"""
    <div style="
        position: fixed;
        bottom: 30px;
        left: 30px;
        z-index: 1000;
        background: white;
        padding: 8px 12px;
        border: 1px solid #999;
        border-radius: 4px;
        font: 13px Arial, sans-serif;
        line-height: 1.6;
        box-shadow: 1px 1px 4px rgba(0,0,0,0.2);
    ">
        <b>A — Going Dark</b><br>
        <span style="color:{ORIGIN_COLOR};">&#9679;</span> Last known position<br>
        <span style="color:{DEST_COLOR};">&#9679;</span> Reappearance<br>
        <span style="color:{LINE_COLOR};">&#9644;</span> Blackout path
    </div>
    """
    fmap.get_root().html.add_child(folium.Element(legend_html))

    output_html.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(output_html))
    print(f"Going dark map saved to: {output_html}  ({len(events)} events)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build going dark anomaly A map")
    parser.add_argument(
        "--input", type=Path, default=DEFAULT_INPUT_CSV,
        help="Path to going dark CSV.",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT_HTML,
        help="Path to save HTML map.",
    )
    args = parser.parse_args()
    build_going_dark_map(args.input, args.output)
