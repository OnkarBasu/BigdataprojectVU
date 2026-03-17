"""
Visualize going dark (Anomaly A) events on a world map.

Loads top_going_dark_vessel_map.csv and plots origin/destination points
with connecting lines. Origin = orange, Destination = purple.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import folium

DEFAULT_CSV_PATH = Path("data/output/top_going_dark_vessel_map.csv")
DEFAULT_OUTPUT_PATH = Path("visualization/going_dark_map.html")

ORIGIN_COLOR = "#ff7f0e"
DESTINATION_COLOR = "#9467bd"
LINE_COLOR = "#8c564b"
LINE_WEIGHT = 4
MARKER_RADIUS = 10


def load_going_dark_data(csv_path: Path) -> pd.DataFrame:
    """
    Load going dark events from CSV.

    Args:
        csv_path: Path to top_going_dark_vessel_map.csv.

    Returns:
        DataFrame with lat_origin, lon_origin, lat_destination, lon_destination,
        and optional event_index, gap_hours, distance_km.

    Raises:
        FileNotFoundError: If CSV does not exist.
        ValueError: If required columns are missing.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    df = pd.read_csv(csv_path)

    required = ["lat_origin", "lon_origin", "lat_destination", "lon_destination"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    return df


def create_going_dark_map(
    df: pd.DataFrame,
    output_path: Path,
) -> None:
    """
    Create an interactive world map with going dark origin/destination points
    and connecting lines.

    Each event is shown as:
    - Orange circle at the last known position before AIS blackout (origin)
    - Purple circle at the first known position after AIS blackout (destination)
    - Brown line connecting the two points
    Clicking or hovering either dot or the line shows event details.

    Args:
        df: DataFrame from load_going_dark_data().
        output_path: Path to save the HTML map.
    """
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
        gap_hours = row.get("gap_hours", pd.NA)
        dist_km = row.get("distance_km", pd.NA)
        mmsi = row.get("mmsi", pd.NA)

        extra = []
        if pd.notna(mmsi):
            extra.append(f"MMSI: {mmsi}")
        if pd.notna(gap_hours):
            extra.append(f"AIS blackout: {float(gap_hours):.2f} h")
        if pd.notna(dist_km):
            extra.append(f"Distance moved: {float(dist_km):.2f} km")
        extra_str = " | ".join(extra) if extra else ""

        origin_text = (
            f"<b>Last position before blackout</b> (Event {event_idx})<br>"
            + (f"{extra_str}<br>" if extra_str else "")
        )
        dest_text = (
            f"<b>First position after blackout</b> (Event {event_idx})<br>"
            + (f"{extra_str}<br>" if extra_str else "")
        )
        line_text = (
            f"<b>Going Dark — Event {event_idx}</b><br>"
            f"Last known → Reappearance<br>"
            + (extra_str if extra_str else "")
        )

        origin_marker = folium.CircleMarker(
            location=[lat_orig, lon_orig],
            radius=MARKER_RADIUS,
            color="black",
            fill=True,
            fill_color=ORIGIN_COLOR,
            fill_opacity=1.0,
            weight=2,
        )
        origin_marker.add_child(
            folium.Tooltip(origin_text, sticky=True, permanent=False)
        )
        origin_marker.add_child(
            folium.Popup(origin_text, max_width=300)
        )
        origin_marker.add_to(m)

        dest_marker = folium.CircleMarker(
            location=[lat_dest, lon_dest],
            radius=MARKER_RADIUS,
            color="black",
            fill=True,
            fill_color=DESTINATION_COLOR,
            fill_opacity=1.0,
            weight=2,
        )
        dest_marker.add_child(
            folium.Tooltip(dest_text, sticky=True, permanent=False)
        )
        dest_marker.add_child(
            folium.Popup(dest_text, max_width=300)
        )
        dest_marker.add_to(m)

        line = folium.PolyLine(
            locations=[[lat_orig, lon_orig], [lat_dest, lon_dest]],
            color=LINE_COLOR,
            weight=LINE_WEIGHT,
            opacity=0.8,
        )
        line.add_child(
            folium.Tooltip(line_text, sticky=True, permanent=False)
        )
        line.add_child(
            folium.Popup(line_text, max_width=300)
        )
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
        max-width: 320px !important;
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
        <p style="margin: 0 0 5px 0;"><b>Anomaly A (Going Dark)</b></p>
        <p style="margin: 0 0 3px 0;">
            <span style="color: {ORIGIN_COLOR}; font-weight: bold;">●</span> Last position before blackout
        </p>
        <p style="margin: 0 0 3px 0;">
            <span style="color: {DESTINATION_COLOR}; font-weight: bold;">●</span> First position after blackout
        </p>
        <p style="margin: 5px 0 0 0; font-size: 12px;">Lines = AIS blackout gaps</p>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(output_path))


def main() -> None:
    """Run the going dark map visualization."""
    parser = argparse.ArgumentParser(
        description="Plot top Anomaly A vessel going dark events on a world map.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help="Path to top_going_dark_vessel_map.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to save the HTML map.",
    )
    args = parser.parse_args()

    df = load_going_dark_data(args.input)

    if df.empty:
        print("No going dark events to plot. CSV is empty.")
        return

    create_going_dark_map(df, args.output)
    print(f"Map saved to: {args.output}")
    print(f"Open in a browser to view {len(df)} going dark event(s).")


if __name__ == "__main__":
    main()
