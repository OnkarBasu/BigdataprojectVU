"""
Visualize anomaly D events on a world map.

Loads top_teleportation_vessel_map.csv and plots origin/destination points
with connecting lines. D1 and D2 subtypes are distinguished visually.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import folium
import pandas as pd

DEFAULT_CSV_PATH = Path("data/output/top_teleportation_vessel_map.csv")
DEFAULT_OUTPUT_PATH = Path("visualization/output/teleportation_map.html")

D1_ORIGIN_COLOR = "#2ca02c"
D1_DESTINATION_COLOR = "#d62728"
D1_LINE_COLOR = "#1f77b4"

D2_ORIGIN_COLOR = "#17becf"
D2_DESTINATION_COLOR = "#ff7f0e"
D2_LINE_COLOR = "#9467bd"

LINE_WEIGHT = 4
MARKER_RADIUS = 10


def load_teleportation_data(csv_path: Path) -> pd.DataFrame:
    """Load anomaly D events from CSV."""
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    df = pd.read_csv(csv_path)

    required = ["lat_origin", "lon_origin", "lat_destination", "lon_destination"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    if "subtype" not in df.columns:
        df["subtype"] = "D"

    return df


def _style_for_subtype(subtype: str) -> tuple[str, str, str, str]:
    subtype_normalized = str(subtype).strip().upper()
    if subtype_normalized == "D1":
        return (
            D1_ORIGIN_COLOR,
            D1_DESTINATION_COLOR,
            D1_LINE_COLOR,
            "D1 — Near-simultaneous cloning",
        )
    if subtype_normalized == "D2":
        return (
            D2_ORIGIN_COLOR,
            D2_DESTINATION_COLOR,
            D2_LINE_COLOR,
            "D2 — Impossible relocation",
        )
    return (
        D1_ORIGIN_COLOR,
        D1_DESTINATION_COLOR,
        D1_LINE_COLOR,
        "D — Teleportation",
    )


def create_teleportation_map(
    df: pd.DataFrame,
    output_path: Path,
) -> None:
    """Create an interactive world map with anomaly D origin/destination points."""
    if df.empty:
        return

    df = df.copy()
    for col in ["lat_origin", "lon_origin", "lat_destination", "lon_destination"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["lat_origin", "lon_origin", "lat_destination", "lon_destination"])
    if df.empty:
        return

    all_lats = pd.concat([df["lat_origin"], df["lat_destination"]])
    all_lons = pd.concat([df["lon_origin"], df["lon_destination"]])
    south, north = float(all_lats.min()), float(all_lats.max())
    west, east = float(all_lons.min()), float(all_lons.max())

    lat_span = north - south if north != south else 0.02
    lon_span = east - west if east != west else 0.02
    pad_lat = max(0.005, lat_span * 0.15)
    pad_lon = max(0.005, lon_span * 0.15)
    bounds = [[south - pad_lat, west - pad_lon], [north + pad_lat, east + pad_lon]]
    center_lat = (south + north) / 2
    center_lon = (west + east) / 2

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles="OpenStreetMap",
        min_zoom=2,
        max_zoom=19,
        control_scale=True,
    )

    for idx, row in df.iterrows():
        lat_orig = float(row["lat_origin"])
        lon_orig = float(row["lon_origin"])
        lat_dest = float(row["lat_destination"])
        lon_dest = float(row["lon_destination"])

        event_idx = row.get("event_index", idx + 1)
        speed = row.get("implied_speed_knots", pd.NA)
        dist_km = row.get("distance_km", pd.NA)
        mmsi = row.get("mmsi", pd.NA)
        subtype = row.get("subtype", "D")

        origin_color, dest_color, line_color, subtype_label = _style_for_subtype(subtype)

        extra = [f"Type: {subtype_label}"]
        if pd.notna(speed):
            extra.append(f"Implied speed: {float(speed):.1f} knots")
        if pd.notna(dist_km):
            extra.append(f"Distance: {float(dist_km):.2f} km")
        if pd.notna(mmsi):
            extra.append(f"MMSI: {mmsi}")
        extra_str = " | ".join(extra)

        origin_text = (
            f"<b>{subtype_label}</b> — Origin (Event {event_idx})<br>"
            + f"{extra_str}<br>"
        )
        dest_text = (
            f"<b>{subtype_label}</b> — Destination (Event {event_idx})<br>"
            + f"{extra_str}<br>"
        )
        line_text = (
            f"<b>{subtype_label} — Event {event_idx}</b><br>Origin → Destination<br>"
            + extra_str
        )

        origin_marker = folium.CircleMarker(
            location=[lat_orig, lon_orig],
            radius=MARKER_RADIUS,
            color="black",
            fill=True,
            fill_color=origin_color,
            fill_opacity=1.0,
            weight=2,
        )
        origin_marker.add_child(folium.Tooltip(origin_text, sticky=True, permanent=False))
        origin_marker.add_child(folium.Popup(origin_text, max_width=320))
        origin_marker.add_to(m)

        dest_marker = folium.CircleMarker(
            location=[lat_dest, lon_dest],
            radius=MARKER_RADIUS,
            color="black",
            fill=True,
            fill_color=dest_color,
            fill_opacity=1.0,
            weight=2,
        )
        dest_marker.add_child(folium.Tooltip(dest_text, sticky=True, permanent=False))
        dest_marker.add_child(folium.Popup(dest_text, max_width=320))
        dest_marker.add_to(m)

        line = folium.PolyLine(
            locations=[[lat_orig, lon_orig], [lat_dest, lon_dest]],
            color=line_color,
            weight=LINE_WEIGHT,
            opacity=0.8,
        )
        line.add_child(folium.Tooltip(line_text, sticky=True, permanent=False))
        line.add_child(folium.Popup(line_text, max_width=320))
        line.add_to(m)

    m.fit_bounds(bounds, padding=[30, 30])

    tooltip_css = """
    <style>
    .leaflet-tooltip {
        font-size: 13px !important;
        font-weight: 500 !important;
        padding: 8px 12px !important;
        background-color: rgba(255, 255, 255, 0.95) !important;
        border: 2px solid #333 !important;
        border-radius: 4px !important;
        box-shadow: 2px 2px 6px rgba(0,0,0,0.3) !important;
        max-width: 340px !important;
    }
    </style>
    """
    m.get_root().html.add_child(folium.Element(tooltip_css))

    legend_html = f"""
    <div style="
        position: fixed;
        bottom: 50px;
        left: 50px;
        z-index: 1000;
        background-color: white;
        padding: 10px 15px;
        border: 2px solid grey;
        border-radius: 5px;
        font-family: Arial;
        font-size: 14px;
    ">
        <p style="margin: 0 0 5px 0;"><b>Anomaly D</b></p>
        <p style="margin: 0 0 3px 0;"><span style="color: {D1_ORIGIN_COLOR}; font-weight: bold;">●</span> D1 origin</p>
        <p style="margin: 0 0 3px 0;"><span style="color: {D1_DESTINATION_COLOR}; font-weight: bold;">●</span> D1 destination</p>
        <p style="margin: 0 0 3px 0;"><span style="color: {D2_ORIGIN_COLOR}; font-weight: bold;">●</span> D2 origin</p>
        <p style="margin: 0 0 3px 0;"><span style="color: {D2_DESTINATION_COLOR}; font-weight: bold;">●</span> D2 destination</p>
        <p style="margin: 5px 0 0 0; font-size: 12px;">Lines = anomaly D transitions</p>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(output_path))


def main() -> None:
    """Run the anomaly D map visualization."""
    parser = argparse.ArgumentParser(
        description="Plot top anomaly D vessel events on a world map.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help="Path to top_teleportation_vessel_map.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to save the HTML map.",
    )
    args = parser.parse_args()

    df = load_teleportation_data(args.input)

    if df.empty:
        print("No anomaly D events to plot. CSV is empty.")
        return

    create_teleportation_map(df, args.output)
    print(f"Map saved to: {args.output}")
    print(f"Open in a browser to view {len(df)} anomaly D event(s).")


if __name__ == "__main__":
    main()
