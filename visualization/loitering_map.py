"""
Visualize anomaly B (loitering & transfers) events on a world map.

Loads top_loitering_vessel_map.csv and plots both vessels' start and end
positions with connecting tracks.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import folium
import pandas as pd

DEFAULT_CSV_PATH = Path("data/output/top_loitering_vessel_map.csv")
DEFAULT_OUTPUT_PATH = Path("visualization/output/loitering_map.html")

VESSEL_A_COLOR = "#1f77b4"
VESSEL_B_COLOR = "#d62728"
TRACK_A_COLOR = "#17becf"
TRACK_B_COLOR = "#ff9896"
MARKER_RADIUS = 9
LINE_WEIGHT = 4


def load_loitering_data(csv_path: Path) -> pd.DataFrame:
    """Load anomaly B events from CSV."""
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    df = pd.read_csv(csv_path)
    required = [
        "mmsi_a",
        "mmsi_b",
        "start_lat_a",
        "start_lon_a",
        "start_lat_b",
        "start_lon_b",
        "end_lat_a",
        "end_lon_a",
        "end_lat_b",
        "end_lon_b",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    return df


def create_loitering_map(df: pd.DataFrame, output_path: Path) -> None:
    """Create an interactive world map with anomaly B paired vessel events."""
    if df.empty:
        return

    df = df.copy()
    coord_cols = [
        "start_lat_a",
        "start_lon_a",
        "start_lat_b",
        "start_lon_b",
        "end_lat_a",
        "end_lon_a",
        "end_lat_b",
        "end_lon_b",
    ]
    for col in coord_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=coord_cols)
    if df.empty:
        return

    all_lats = pd.concat(
        [df["start_lat_a"], df["start_lat_b"], df["end_lat_a"], df["end_lat_b"]]
    )
    all_lons = pd.concat(
        [df["start_lon_a"], df["start_lon_b"], df["end_lon_a"], df["end_lon_b"]]
    )
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
        event_idx = row.get("event_index", idx + 1)
        focus_mmsi = row.get("focus_mmsi", pd.NA)
        mmsi_a = row.get("mmsi_a", pd.NA)
        mmsi_b = row.get("mmsi_b", pd.NA)
        duration_hours = row.get("duration_hours", pd.NA)
        min_distance_km = row.get("min_distance_km", pd.NA)
        avg_distance_km = row.get("avg_distance_km", pd.NA)
        start_timestamp = row.get("start_timestamp", "")
        end_timestamp = row.get("end_timestamp", "")

        extra = []
        if pd.notna(focus_mmsi):
            extra.append(f"Focus MMSI: {focus_mmsi}")
        if pd.notna(duration_hours):
            extra.append(f"Duration: {float(duration_hours):.2f} h")
        if pd.notna(min_distance_km):
            extra.append(f"Min distance: {float(min_distance_km):.3f} km")
        if pd.notna(avg_distance_km):
            extra.append(f"Avg distance: {float(avg_distance_km):.3f} km")
        if start_timestamp and end_timestamp:
            extra.append(f"{start_timestamp} → {end_timestamp}")
        extra_str = " | ".join(extra)

        start_a = [float(row["start_lat_a"]), float(row["start_lon_a"])]
        end_a = [float(row["end_lat_a"]), float(row["end_lon_a"])]
        start_b = [float(row["start_lat_b"]), float(row["start_lon_b"])]
        end_b = [float(row["end_lat_b"]), float(row["end_lon_b"])]

        tooltip_start_a = f"<b>Event {event_idx} — Vessel A start</b><br>MMSI: {mmsi_a}<br>{extra_str}"
        tooltip_end_a = f"<b>Event {event_idx} — Vessel A end</b><br>MMSI: {mmsi_a}<br>{extra_str}"
        tooltip_start_b = f"<b>Event {event_idx} — Vessel B start</b><br>MMSI: {mmsi_b}<br>{extra_str}"
        tooltip_end_b = f"<b>Event {event_idx} — Vessel B end</b><br>MMSI: {mmsi_b}<br>{extra_str}"
        line_a_text = f"<b>Event {event_idx} — Vessel A track</b><br>MMSI: {mmsi_a}<br>{extra_str}"
        line_b_text = f"<b>Event {event_idx} — Vessel B track</b><br>MMSI: {mmsi_b}<br>{extra_str}"

        for location, fill_color, text in [
            (start_a, VESSEL_A_COLOR, tooltip_start_a),
            (end_a, TRACK_A_COLOR, tooltip_end_a),
            (start_b, VESSEL_B_COLOR, tooltip_start_b),
            (end_b, TRACK_B_COLOR, tooltip_end_b),
        ]:
            marker = folium.CircleMarker(
                location=location,
                radius=MARKER_RADIUS,
                color="black",
                fill=True,
                fill_color=fill_color,
                fill_opacity=1.0,
                weight=2,
            )
            marker.add_child(folium.Tooltip(text, sticky=True, permanent=False))
            marker.add_child(folium.Popup(text, max_width=360))
            marker.add_to(m)

        line_a = folium.PolyLine(
            locations=[start_a, end_a],
            color=TRACK_A_COLOR,
            weight=LINE_WEIGHT,
            opacity=0.85,
        )
        line_a.add_child(folium.Tooltip(line_a_text, sticky=True, permanent=False))
        line_a.add_child(folium.Popup(line_a_text, max_width=360))
        line_a.add_to(m)

        line_b = folium.PolyLine(
            locations=[start_b, end_b],
            color=TRACK_B_COLOR,
            weight=LINE_WEIGHT,
            opacity=0.85,
        )
        line_b.add_child(folium.Tooltip(line_b_text, sticky=True, permanent=False))
        line_b.add_child(folium.Popup(line_b_text, max_width=360))
        line_b.add_to(m)

        bridge = folium.PolyLine(
            locations=[start_a, start_b],
            color="#555555",
            weight=2,
            opacity=0.5,
            dash_array="4,6",
        )
        bridge.add_child(
            folium.Tooltip(
                f"<b>Event {event_idx} — proximity link</b><br>{extra_str}",
                sticky=True,
                permanent=False,
            )
        )
        bridge.add_to(m)

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
        max-width: 360px !important;
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
        <p style="margin: 0 0 5px 0;"><b>Anomaly B (Loitering & Transfers)</b></p>
        <p style="margin: 0 0 3px 0;"><span style="color: {VESSEL_A_COLOR}; font-weight: bold;">●</span> Vessel A start</p>
        <p style="margin: 0 0 3px 0;"><span style="color: {TRACK_A_COLOR}; font-weight: bold;">●</span> Vessel A end / track</p>
        <p style="margin: 0 0 3px 0;"><span style="color: {VESSEL_B_COLOR}; font-weight: bold;">●</span> Vessel B start</p>
        <p style="margin: 0 0 3px 0;"><span style="color: {TRACK_B_COLOR}; font-weight: bold;">●</span> Vessel B end / track</p>
        <p style="margin: 5px 0 0 0; font-size: 12px;">Dashed line = initial proximity</p>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(output_path))


def main() -> None:
    """Run the anomaly B map visualization."""
    parser = argparse.ArgumentParser(
        description="Plot top anomaly B vessel events on a world map.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help="Path to top_loitering_vessel_map.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to save the HTML map.",
    )
    args = parser.parse_args()

    df = load_loitering_data(args.input)

    if df.empty:
        print("No anomaly B events to plot. CSV is empty.")
        return

    create_loitering_map(df, args.output)
    print(f"Map saved to: {args.output}")
    print(f"Open in a browser to view {len(df)} anomaly B event(s).")


if __name__ == "__main__":
    main()
