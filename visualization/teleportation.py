"""
Visualize anomaly D teleportation events on interactive world maps.

Generates two HTML maps:
  - teleportation_d1_map.html  D1 — vessel identity map (Vessel A vs Vessel B)
  - teleportation_d2_map.html  D2 — impossible relocation jump map

D1 logic: every ping is assigned to a physical vessel by geographic cluster,
not by which came first. Vessel A (blue) = Denmark cluster, Vessel B (orange)
= Baltic cluster. Dashed lines connect the simultaneous paired positions,
proving one MMSI was in two places at once.

Usage:
    python visualization/teleportation.py
    python visualization/teleportation.py --d1-input path/to/d1.csv --d2-input path/to/d2.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import folium


# ── Default paths ─────────────────────────────────────────────────────────────
DEFAULT_D1_CSV    = Path("data/output/top_teleportation_d1_vessel_map.csv")
DEFAULT_D2_CSV    = Path("data/output/top_teleportation_d2_vessel_map.csv")
DEFAULT_D1_OUTPUT = Path("visualization/output/teleportation_d1_map.html")
DEFAULT_D2_OUTPUT = Path("visualization/output/teleportation_d2_map.html")

# ── D1 vessel identity colors ─────────────────────────────────────────────────
VESSEL_A_COLOR      = "#1f77b4"   # blue   — Denmark cluster
VESSEL_B_COLOR      = "#ff7f0e"   # orange — Baltic cluster
CONNECTOR_COLOR     = "#888888"   # grey   — simultaneous-ping dashed line

# ── D2 colors ─────────────────────────────────────────────────────────────────
D2_ORIGIN_COLOR = "#17becf"       # cyan
D2_DEST_COLOR   = "#ff7f0e"       # orange
D2_LINE_COLOR   = "#9467bd"       # purple

MARKER_RADIUS = 7
LINE_WEIGHT   = 2


# ── Shared helpers ────────────────────────────────────────────────────────────

def _load_events(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    events = []
    with csv_path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            events.append({
                "mmsi":                int(row["mmsi"]),
                "event_index":         int(row["event_index"]),
                "lat_origin":          float(row["lat_origin"]),
                "lon_origin":          float(row["lon_origin"]),
                "lat_destination":     float(row["lat_destination"]),
                "lon_destination":     float(row["lon_destination"]),
                "implied_speed_knots": float(row["implied_speed_knots"]),
                "distance_km":         float(row["distance_km"]),
            })
    return events


def _bounding_box(events: list[dict]) -> tuple[float, float, float, float]:
    south = north = events[0]["lat_origin"]
    west  = east  = events[0]["lon_origin"]
    for e in events:
        for lk, lnk in (("lat_origin", "lon_origin"), ("lat_destination", "lon_destination")):
            lat, lon = e[lk], e[lnk]
            if lat < south: south = lat
            if lat > north: north = lat
            if lon < west:  west  = lon
            if lon > east:  east  = lon
    return south, north, west, east


def _find_cluster_threshold(lats: list[float]) -> float:
    """Find the latitude of the largest gap — splits points into 2 clusters."""
    sorted_lats = sorted(set(lats))
    max_gap, threshold = -1.0, (sorted_lats[0] + sorted_lats[-1]) / 2
    for i in range(len(sorted_lats) - 1):
        gap = sorted_lats[i + 1] - sorted_lats[i]
        if gap > max_gap:
            max_gap = gap
            threshold = (sorted_lats[i] + sorted_lats[i + 1]) / 2
    return threshold


def _base_map(south: float, north: float, west: float, east: float) -> folium.Map:
    pad_lat = max(0.005, (north - south) * 0.15)
    pad_lon = max(0.005, (east  - west)  * 0.15)
    fmap = folium.Map(
        location=[(south + north) / 2, (west + east) / 2],
        zoom_start=5,
        tiles="CartoDB positron",
        control_scale=True,
    )
    fmap.fit_bounds([[south - pad_lat, west - pad_lon], [north + pad_lat, east + pad_lon]])
    return fmap


# ── D1 — vessel identity map ──────────────────────────────────────────────────

def build_d1_map(input_csv: Path, output_html: Path) -> None:
    """Build the D1 vessel identity map.

    Each ping is assigned to a physical vessel by its geographic cluster:
      Vessel A (blue)   = positions in the southern cluster (e.g. Denmark)
      Vessel B (orange) = positions in the northern cluster (e.g. Baltic Sea)

    A dashed grey line connects the two simultaneous positions per event,
    showing that one MMSI was in two places at once.
    """
    events = _load_events(input_csv)
    if not events:
        print("No D1 events found — skipping.")
        return

    south, north, west, east = _bounding_box(events)

    # Auto-detect cluster boundary from all ping latitudes
    all_lats = [e["lat_origin"] for e in events] + [e["lat_destination"] for e in events]
    threshold = _find_cluster_threshold(all_lats)

    fmap = _base_map(south, north, west, east)

    fg_vessel_a   = folium.FeatureGroup(name="Vessel A — southern cluster")
    fg_vessel_b   = folium.FeatureGroup(name="Vessel B — northern cluster")
    fg_traj_a     = folium.FeatureGroup(name="Vessel A trajectory")
    fg_traj_b     = folium.FeatureGroup(name="Vessel B trajectory")
    fg_connectors = folium.FeatureGroup(name="Simultaneous ping lines")

    vessel_a_coords = []   # all positions belonging to Vessel A
    vessel_b_coords = []   # all positions belonging to Vessel B

    for e in events:
        origin = (e["lat_origin"],      e["lon_origin"])
        dest   = (e["lat_destination"], e["lon_destination"])
        idx    = e["event_index"]
        speed  = e["implied_speed_knots"]
        dist   = e["distance_km"]
        mmsi   = e["mmsi"]

        # Assign each ping to a vessel by cluster, regardless of origin/dest order
        for coord in (origin, dest):
            is_vessel_a = coord[0] < threshold
            color  = VESSEL_A_COLOR if is_vessel_a else VESSEL_B_COLOR
            label  = "Vessel A (southern)"  if is_vessel_a else "Vessel B (northern)"
            fg_dot = fg_vessel_a if is_vessel_a else fg_vessel_b

            tip = (
                f"<b>{label}</b> | Event {idx}<br>"
                f"MMSI: {mmsi}<br>"
                f"({coord[0]:.5f}, {coord[1]:.5f})<br>"
                f"{speed:.1f} kn | {dist:.1f} km"
            )
            folium.CircleMarker(
                location=coord, radius=MARKER_RADIUS,
                color="black", fill=True, fill_color=color,
                fill_opacity=0.9, weight=1, tooltip=tip,
            ).add_to(fg_dot)

            if is_vessel_a:
                vessel_a_coords.append(coord)
            else:
                vessel_b_coords.append(coord)

        # Dashed connector line between the two simultaneous positions
        folium.PolyLine(
            locations=[origin, dest],
            color=CONNECTOR_COLOR,
            weight=1,
            opacity=0.6,
            dash_array="6 4",
            tooltip=(
                f"<b>Same MMSI, same time — Event {idx}</b><br>"
                f"MMSI: {mmsi} | {speed:.1f} kn | {dist:.1f} km<br>"
                f"Impossible for one ship → two vessels"
            ),
        ).add_to(fg_connectors)

    # Smooth trajectory within each cluster (sorted by latitude)
    for coords, color, fg, label in [
        (vessel_a_coords, VESSEL_A_COLOR, fg_traj_a, "Vessel A trajectory"),
        (vessel_b_coords, VESSEL_B_COLOR, fg_traj_b, "Vessel B trajectory"),
    ]:
        # Split into south/north sub-clusters to avoid cross-cluster lines
        lo = sorted([c for c in coords if c[0] < threshold], key=lambda c: c[0])
        hi = sorted([c for c in coords if c[0] >= threshold], key=lambda c: c[0])
        for seg in (lo, hi):
            if len(seg) > 1:
                folium.PolyLine(
                    locations=seg, color=color,
                    weight=LINE_WEIGHT + 1, opacity=0.85, tooltip=label,
                ).add_to(fg)

    for fg in (fg_connectors, fg_traj_a, fg_traj_b, fg_vessel_a, fg_vessel_b):
        fg.add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)

    fmap.get_root().html.add_child(folium.Element(f"""
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;background:white;
        padding:8px 14px;border:1px solid #999;border-radius:4px;
        font:13px Arial,sans-serif;line-height:1.8;
        box-shadow:1px 1px 4px rgba(0,0,0,0.2);">
        <b>D1 — Near-Simultaneous Cloning</b><br>
        <span style="color:{VESSEL_A_COLOR};">&#9679;</span> Vessel A — southern cluster<br>
        <span style="color:{VESSEL_B_COLOR};">&#9679;</span> Vessel B — northern cluster<br>
        <span style="color:{CONNECTOR_COLOR};">- - -</span> Same MMSI, same time (two ships)<br>
        <span style="font-size:11px;color:#aaa;">Cluster split at {threshold:.2f}°N</span>
    </div>
    """))

    output_html.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(output_html))
    print(f"D1 map saved → {output_html}  ({len(events)} events, threshold={threshold:.2f}°N)")


# ── D2 — impossible relocation map ───────────────────────────────────────────

def build_d2_map(input_csv: Path, output_html: Path) -> None:
    """Build the D2 impossible relocation map.

    Shows last known position → reappearance position as origin/destination
    markers connected by a jump line. Gap is 30 min–24 h.
    """
    events = _load_events(input_csv)
    if not events:
        print("No D2 events found — skipping.")
        return

    south, north, west, east = _bounding_box(events)
    fmap = _base_map(south, north, west, east)

    fg_origins = folium.FeatureGroup(name="Last known positions")
    fg_dests   = folium.FeatureGroup(name="Reappearance positions")
    fg_lines   = folium.FeatureGroup(name="Jump lines")

    for e in events:
        origin = (e["lat_origin"],      e["lon_origin"])
        dest   = (e["lat_destination"], e["lon_destination"])
        idx    = e["event_index"]
        speed  = e["implied_speed_knots"]
        dist   = e["distance_km"]
        mmsi   = e["mmsi"]

        folium.CircleMarker(
            location=origin, radius=MARKER_RADIUS,
            color="black", fill=True, fill_color=D2_ORIGIN_COLOR,
            fill_opacity=0.9, weight=1,
            tooltip=(
                f"<b>Last known position</b> | Event {idx}<br>"
                f"MMSI: {mmsi}<br>({origin[0]:.5f}, {origin[1]:.5f})<br>"
                f"{speed:.1f} kn | {dist:.1f} km"
            ),
        ).add_to(fg_origins)

        folium.CircleMarker(
            location=dest, radius=MARKER_RADIUS,
            color="black", fill=True, fill_color=D2_DEST_COLOR,
            fill_opacity=0.9, weight=1,
            tooltip=(
                f"<b>Reappearance</b> | Event {idx}<br>"
                f"MMSI: {mmsi}<br>({dest[0]:.5f}, {dest[1]:.5f})<br>"
                f"{speed:.1f} kn | {dist:.1f} km"
            ),
        ).add_to(fg_dests)

        folium.PolyLine(
            locations=[origin, dest], color=D2_LINE_COLOR,
            weight=LINE_WEIGHT, opacity=0.7,
            tooltip=f"D2 Event {idx} | MMSI {mmsi} | {speed:.1f} kn | {dist:.1f} km",
        ).add_to(fg_lines)

    for fg in (fg_lines, fg_origins, fg_dests):
        fg.add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)

    fmap.get_root().html.add_child(folium.Element(f"""
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;background:white;
        padding:8px 14px;border:1px solid #999;border-radius:4px;
        font:13px Arial,sans-serif;line-height:1.8;
        box-shadow:1px 1px 4px rgba(0,0,0,0.2);">
        <b>D2 — Impossible Relocation</b><br>
        <span style="color:{D2_ORIGIN_COLOR};">&#9679;</span> Last known position<br>
        <span style="color:{D2_DEST_COLOR};">&#9679;</span> Reappearance<br>
        <span style="color:{D2_LINE_COLOR};">&#9644;</span> Jump line
    </div>
    """))

    output_html.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(output_html))
    print(f"D2 map saved → {output_html}  ({len(events)} events)")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate D1 and D2 teleportation maps.")
    parser.add_argument("--d1-input",  type=Path, default=DEFAULT_D1_CSV)
    parser.add_argument("--d2-input",  type=Path, default=DEFAULT_D2_CSV)
    parser.add_argument("--d1-output", type=Path, default=DEFAULT_D1_OUTPUT)
    parser.add_argument("--d2-output", type=Path, default=DEFAULT_D2_OUTPUT)
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