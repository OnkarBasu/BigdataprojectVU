from __future__ import annotations

import csv
from pathlib import Path

import folium


def build_going_dark_map(
    input_csv: Path,
    output_html: Path,
) -> None:
    """
    Build an interactive map for anomaly A (Going Dark events).

    Args:
        input_csv: CSV file with going dark events.
        output_html: Output HTML file.
    """

    if not input_csv.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")

    events = []

    with input_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            events.append(
                {
                    "mmsi": int(row["mmsi"]),
                    "event_index": int(row["event_index"]),
                    "lat_origin": float(row["lat_origin"]),
                    "lon_origin": float(row["lon_origin"]),
                    "lat_destination": float(row["lat_destination"]),
                    "lon_destination": float(row["lon_destination"]),
                    "gap_hours": float(row["gap_hours"]),
                    "distance_km": float(row["distance_km"]),
                }
            )

    if not events:
        print("No going dark events found.")
        return

    # Center map
    avg_lat = sum(e["lat_origin"] for e in events) / len(events)
    avg_lon = sum(e["lon_origin"] for e in events) / len(events)

    fmap = folium.Map(location=[avg_lat, avg_lon], zoom_start=6)

    for event in events:
        origin = (event["lat_origin"], event["lon_origin"])
        destination = (event["lat_destination"], event["lon_destination"])

        popup_text = (
            f"<b>MMSI:</b> {event['mmsi']}<br>"
            f"<b>Event:</b> {event['event_index']}<br>"
            f"<b>Gap (hours):</b> {event['gap_hours']:.2f}<br>"
            f"<b>Distance (km):</b> {event['distance_km']:.2f}"
        )

        # Origin marker
        folium.CircleMarker(
            location=origin,
            radius=4,
            color="blue",
            fill=True,
            fill_opacity=0.7,
            tooltip="Origin",
            popup=popup_text,
        ).add_to(fmap)

        # Destination marker
        folium.CircleMarker(
            location=destination,
            radius=4,
            color="red",
            fill=True,
            fill_opacity=0.7,
            tooltip="Destination",
            popup=popup_text,
        ).add_to(fmap)

        # Line between points
        folium.PolyLine(
            locations=[origin, destination],
            color="orange",
            weight=2,
            opacity=0.7,
        ).add_to(fmap)

    output_html.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(output_html))

    print(f"Going dark map saved to: {output_html}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build going dark map")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/output/top_going_dark_vessel_map.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("visualization/output/going_dark_map.html"),
    )

    args = parser.parse_args()

    build_going_dark_map(args.input, args.output)