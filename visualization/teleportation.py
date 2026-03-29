"""
Visualize anomaly D teleportation events on interactive world maps.

Generates two separate HTML maps:
  - D1 (near-simultaneous cloning): green origin, red destination, blue line
  - D2 (impossible relocation):     cyan origin, orange destination, purple line

Each map is a scrollable Folium world map with layer controls.
Hovering on any marker or line shows MMSI, implied speed, distance, and event index.

Usage:
    python visualization/teleportation.py
    python visualization/teleportation.py --d1-input path/to/d1.csv --d2-input path/to/d2.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import folium
from folium.plugins import MarkerCluster


# ── Default paths ────────────────────────────────────────────────────────────
DEFAULT_D1_CSV = Path("data/output/top_teleportation_d1_vessel_map.csv")
DEFAULT_D2_CSV = Path("data/output/top_teleportation_d2_vessel_map.csv")
DEFAULT_D1_OUTPUT = Path("visualization/output/teleportation_d1_map.html")
DEFAULT_D2_OUTPUT = Path("visualization/output/teleportation_d2_map.html")

# ── D1 colors ────────────────────────────────────────────────────────────────
D1_ORIGIN_COLOR = "#2ca02c"       # green
D1_DEST_COLOR = "#d62728"         # red
D1_LINE_COLOR = "#1f77b4"         # blue

# ── D2 colors ────────────────────────────────────────────────────────────────
D2_ORIGIN_COLOR = "#17becf"       # cyan
D2_DEST_COLOR = "#ff7f0e"         # orange
D2_LINE_COLOR = "#9467bd"         # purple

MARKER_RADIUS = 7
LINE_WEIGHT = 2


def _load_events(csv_path: Path) -> list[dict]:
    """Load teleportation events from a CSV file into a list of dicts."""
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    events = []
    with csv_path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            events.append({
                "mmsi": int(row["mmsi"]),
                "event_index": int(row["event_index"]),
                "lat_origin": float(row["lat_origin"]),
                "lon_origin": float(row["lon_origin"]),
                "lat_destination": float(row["lat_destination"]),
                "lon_destination": float(row["lon_destination"]),
                "implied_speed_knots": float(row["implied_speed_knots"]),
                "distance_km": float(row["distance_km"]),
            })
    return events


def _build_map(
    events: list[dict],
    origin_color: str,
    dest_color: str,
    line_color: str,
    subtype_label: str,
    origin_label: str,
    dest_label: str,
) -> folium.Map:
    """Build a Folium map from a list of teleportation events."""

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
        zoom_start=5,
        tiles="CartoDB positron",
        control_scale=True,
    )

    # Feature groups for layer control
    fg_origins = folium.FeatureGroup(name=f"{origin_label}s")
    fg_dests = folium.FeatureGroup(name=f"{dest_label}s")
    fg_lines = folium.FeatureGroup(name="Jump lines")

    for event in events:
        origin = (event["lat_origin"], event["lon_origin"])
        dest = (event["lat_destination"], event["lon_destination"])
        idx = event["event_index"]
        speed = event["implied_speed_knots"]
        dist = event["distance_km"]
        mmsi = event["mmsi"]

        origin_tip = (
            f"<b>{origin_label}</b> | Event {idx}<br>"
            f"MMSI: {mmsi}<br>"
            f"({origin[0]:.5f}, {origin[1]:.5f})<br>"
            f"{speed:.1f} kn | {dist:.1f} km"
        )
        dest_tip = (
            f"<b>{dest_label}</b> | Event {idx}<br>"
            f"MMSI: {mmsi}<br>"
            f"({dest[0]:.5f}, {dest[1]:.5f})<br>"
            f"{speed:.1f} kn | {dist:.1f} km"
        )
        line_tip = (
            f"<b>{subtype_label} — Event {idx}</b><br>"
            f"MMSI: {mmsi}<br>"
            f"{speed:.1f} kn | {dist:.1f} km"
        )

        # Origin marker
        folium.CircleMarker(
            location=origin,
            radius=MARKER_RADIUS,
            color="black",
            fill=True,
            fill_color=origin_color,
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
            fill_color=dest_color,
            fill_opacity=0.9,
            weight=1,
            tooltip=dest_tip,
        ).add_to(fg_dests)

        # Connecting line
        folium.PolyLine(
            locations=[origin, dest],
            color=line_color,
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
        <b>{subtype_label}</b><br>
        <span style="color:{origin_color};">&#9679;</span> {origin_label}<br>
        <span style="color:{dest_color};">&#9679;</span> {dest_label}<br>
        <span style="color:{line_color};">&#9644;</span> Jump line
    </div>
    """
    fmap.get_root().html.add_child(folium.Element(legend_html))

    return fmap


def build_d1_map(input_csv: Path, output_html: Path) -> None:
    """Build the D1 (near-simultaneous cloning) interactive map."""
    events = _load_events(input_csv)
    if not events:
        print("No D1 events found — skipping D1 map.")
        return

    fmap = _build_map(
        events=events,
        origin_color=D1_ORIGIN_COLOR,
        dest_color=D1_DEST_COLOR,
        line_color=D1_LINE_COLOR,
        subtype_label="D1 — Near-Simultaneous Cloning",
        origin_label="Before (earlier ping)",
        dest_label="After (later ping)",
    )

    output_html.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(output_html))
    print(f"D1 map saved to: {output_html}  ({len(events)} events)")


def build_d2_map(input_csv: Path, output_html: Path) -> None:
    """Build the D2 (impossible relocation) interactive map."""
    events = _load_events(input_csv)
    if not events:
        print("No D2 events found — skipping D2 map.")
        return

    fmap = _build_map(
        events=events,
        origin_color=D2_ORIGIN_COLOR,
        dest_color=D2_DEST_COLOR,
        line_color=D2_LINE_COLOR,
        subtype_label="D2 — Impossible Relocation",
        origin_label="Last known position",
        dest_label="Reappearance position",
    )

    output_html.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(output_html))
    print(f"D2 map saved to: {output_html}  ({len(events)} events)")


def main() -> None:
    """Generate both D1 and D2 teleportation maps."""
    parser = argparse.ArgumentParser(
        description="Generate D1 and D2 teleportation anomaly maps.",
    )
    parser.add_argument(
        "--d1-input", type=Path, default=DEFAULT_D1_CSV,
        help="Path to D1 teleportation CSV.",
    )
    parser.add_argument(
        "--d2-input", type=Path, default=DEFAULT_D2_CSV,
        help="Path to D2 teleportation CSV.",
    )
    parser.add_argument(
        "--d1-output", type=Path, default=DEFAULT_D1_OUTPUT,
        help="Path to save D1 HTML map.",
    )
    parser.add_argument(
        "--d2-output", type=Path, default=DEFAULT_D2_OUTPUT,
        help="Path to save D2 HTML map.",
    )
    args = parser.parse_args()

    if args.d1_input.exists():
        build_d1_map(args.d1_input, args.d1_output)
    else:
        print(f"D1 CSV not found at {args.d1_input} — skipping.")

    if args.d2_input.exists():
        build_d2_map(args.d2_input, args.d2_output)
    else:
        print(f"D2 CSV not found at {args.d2_input} — skipping.")


if __name__ == "__main__":
    main()
