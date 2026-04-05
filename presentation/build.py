"""
Build the self-contained Shadow Fleet Detection HTML presentation.

Reads the three Folium map HTML files, escapes them for srcdoc embedding,
and writes a single presentation/index.html file.

Usage:
    python presentation/build.py
"""

from __future__ import annotations
from pathlib import Path
import html as html_module

ROOT = Path(__file__).parent.parent
MAPS = {
    "going_dark": ROOT / "visualization/output/going_dark_map.html",
    "tele_d1":    ROOT / "visualization/output/teleportation_d1_map.html",
    "tele_d2":    ROOT / "visualization/output/teleportation_d2_map.html",
}
OUT = Path(__file__).parent / "index.html"


def load_srcdoc(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    return html_module.escape(content, quote=True)


def build() -> None:
    print("Reading map files...")
    for key, path in MAPS.items():
        if not path.exists():
            print(f"  WARNING: {path} not found")

    going_dark_src = load_srcdoc(MAPS["going_dark"]) if MAPS["going_dark"].exists() else ""
    tele_d1_src    = load_srcdoc(MAPS["tele_d1"])    if MAPS["tele_d1"].exists()    else ""
    tele_d2_src    = load_srcdoc(MAPS["tele_d2"])    if MAPS["tele_d2"].exists()    else ""

    out = TEMPLATE.replace("%%GOING_DARK%%", going_dark_src) \
                  .replace("%%TELE_D1%%",    tele_d1_src)    \
                  .replace("%%TELE_D2%%",    tele_d2_src)

    OUT.write_text(out, encoding="utf-8")
    print(f"Built: {OUT}  ({OUT.stat().st_size // 1024} KB)")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Shadow Fleet Detection</title>
<style>
/* ── Reset ─────────────────────────────────────────────── */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --red:#e74c3c;--red2:#c0392b;--redglow:rgba(231,76,60,.25);
  --teal:#17becf;--orange:#ff7f0e;--green:#2ecc71;--yellow:#f1c40f;
  --bg:#080d18;--bg2:#0d1526;--bg3:#121e35;
  --glass:rgba(255,255,255,.04);--glassborder:rgba(255,255,255,.09);
  --text:#dde4f0;--muted:#6b7f99;--white:#fff;
  --font:'Segoe UI',system-ui,sans-serif;
  --mono:'Consolas','Fira Code',monospace;
}
html{scroll-behavior:smooth}
body{font-family:var(--font);background:var(--bg);color:var(--text);overflow:hidden}

/* ── Slides ────────────────────────────────────────────── */
.deck{height:100vh;overflow-y:scroll;scroll-snap-type:y mandatory}
.slide{height:100vh;scroll-snap-align:start;position:relative;overflow:hidden;display:flex;flex-direction:column}

/* ── Dot nav ───────────────────────────────────────────── */
.dots{position:fixed;right:20px;top:50%;transform:translateY(-50%);z-index:9999;display:flex;flex-direction:column;gap:10px}
.dots a{width:10px;height:10px;border-radius:50%;background:rgba(255,255,255,.2);display:block;transition:.25s;border:1px solid transparent}
.dots a:hover,.dots a.on{background:var(--red);border-color:var(--red);box-shadow:0 0 8px var(--redglow);transform:scale(1.3)}

/* ── Canvas bg ─────────────────────────────────────────── */
.bg-canvas{position:absolute;inset:0;z-index:0}

/* ── Glow blobs ────────────────────────────────────────── */
.blob{position:absolute;border-radius:50%;filter:blur(90px);opacity:.18;pointer-events:none;z-index:0}

/* ════════════════════════════════════════════════════════
   SLIDE 1 — PIPELINE
════════════════════════════════════════════════════════ */
#s1{background:var(--bg)}
#s1 .blob1{width:500px;height:500px;background:radial-gradient(circle,#c0392b,transparent);top:-100px;left:-100px}
#s1 .blob2{width:400px;height:400px;background:radial-gradient(circle,#17becf,transparent);bottom:-80px;right:5%}

/* hero */
.s1-hero{position:relative;z-index:2;padding:28px 52px 0;flex-shrink:0}
.s1-hero-top{display:flex;align-items:flex-end;justify-content:space-between}
.s1-title{font-size:2.4rem;font-weight:900;letter-spacing:-.01em;line-height:1}
.s1-title span{
  background:linear-gradient(90deg,var(--red),#ff6b6b,var(--orange));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.s1-sub{font-size:.88rem;color:var(--muted);margin-top:5px;max-width:620px;line-height:1.5}
.s1-hint{font-size:.75rem;color:var(--muted);background:var(--glass);border:1px solid var(--glassborder);
  padding:5px 14px;border-radius:20px;letter-spacing:.04em;white-space:nowrap;margin-bottom:4px}
.divider{height:1px;background:linear-gradient(90deg,transparent,rgba(231,76,60,.4),transparent);margin:14px 0}

/* pipeline track */
.pipeline{position:relative;z-index:2;display:flex;align-items:flex-start;justify-content:center;
  gap:0;padding:0 32px;flex:1;overflow:hidden}

/* node */
.pnode{display:flex;flex-direction:column;align-items:center;cursor:pointer;width:210px;flex-shrink:0;
  animation:riseUp .5s ease both}
.pnode:nth-child(1){animation-delay:.05s}
.pnode:nth-child(3){animation-delay:.15s}
.pnode:nth-child(5){animation-delay:.25s}
.pnode:nth-child(7){animation-delay:.35s}
.pnode:nth-child(9){animation-delay:.45s}
@keyframes riseUp{from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:translateY(0)}}

.pcard{
  width:100%;
  background:var(--glass);
  border:1px solid var(--glassborder);
  border-radius:18px;
  padding:22px 20px;
  backdrop-filter:blur(12px);
  transition:border-color .2s,box-shadow .2s,transform .2s;
  position:relative;overflow:hidden}
.pcard::after{content:'';position:absolute;inset:0;border-radius:18px;
  background:linear-gradient(135deg,rgba(231,76,60,.06),transparent);
  opacity:0;transition:opacity .2s}
.pnode:hover .pcard,.pnode.lit .pcard{
  border-color:var(--red);transform:translateY(-5px);
  box-shadow:0 8px 32px var(--redglow),0 0 0 1px rgba(231,76,60,.15)}
.pnode:hover .pcard::after,.pnode.lit .pcard::after{opacity:1}

.pcard-top-bar{height:3px;border-radius:2px;margin-bottom:18px;
  background:linear-gradient(90deg,var(--red),var(--orange))}

.picon{font-size:2.2rem;text-align:center;margin-bottom:10px;
  filter:drop-shadow(0 0 8px rgba(231,76,60,.5))}
.pfile{font-family:var(--mono);font-size:.7rem;color:var(--teal);text-align:center;
  background:rgba(23,190,207,.08);padding:4px 10px;border-radius:5px;margin-bottom:8px;
  letter-spacing:.02em}
.ptitle{font-size:.86rem;font-weight:700;color:var(--white);text-align:center;margin-bottom:14px;
  letter-spacing:.01em}
.pfacts{list-style:none;display:flex;flex-direction:column;gap:9px}
.pfacts li{font-size:.7rem;color:var(--muted);padding-left:14px;position:relative;line-height:1.5}
.pfacts li::before{content:'▸';color:var(--red);position:absolute;left:0;font-size:.62rem;top:2px}
.pmore{margin-top:14px;font-size:.65rem;color:rgba(231,76,60,.55);text-align:center;
  letter-spacing:.08em;text-transform:uppercase;padding-top:10px;
  border-top:1px solid rgba(255,255,255,.05)}

/* connector */
.pconn{display:flex;flex-direction:column;align-items:center;justify-content:center;
  width:44px;flex-shrink:0;gap:6px;padding-top:60px}

/* ── Ship animation ──────────────────────────────────── */
.ship-lane{
  position:relative;z-index:2;height:44px;margin:0 52px;
  overflow:hidden;flex-shrink:0;
  border-bottom:1px solid rgba(23,190,207,.12)}
.wave-strip{
  position:absolute;bottom:0;left:0;
  width:400%;height:6px;
  background:repeating-linear-gradient(
    90deg,
    transparent 0px,transparent 18px,
    rgba(23,190,207,.07) 18px,rgba(23,190,207,.07) 36px);
  animation:wavePan 5s linear infinite}
@keyframes wavePan{from{transform:translateX(0)}to{transform:translateX(-25%)}}
.ship-float{
  position:absolute;bottom:8px;
  display:flex;align-items:center;gap:10px;
  animation:sailRight 18s linear infinite;
  white-space:nowrap}
@keyframes sailRight{
  0%  {left:-260px;opacity:0}
  4%  {opacity:1}
  96% {opacity:1}
  100%{left:110%;opacity:0}}
.ship-svg{font-size:1.7rem;line-height:1;animation:bob .9s ease-in-out infinite alternate}
@keyframes bob{from{transform:translateY(0)}to{transform:translateY(-3px)}}
.ship-label{
  font-size:.65rem;font-weight:800;letter-spacing:.22em;
  color:var(--teal);text-transform:uppercase;
  text-shadow:0 0 14px rgba(23,190,207,.6),0 0 4px rgba(23,190,207,.4);
  animation:bob .9s ease-in-out infinite alternate}
.ship-dots{display:flex;gap:3px;align-items:center}
.ship-dots span{width:4px;height:4px;border-radius:50%;background:var(--teal);opacity:.4;
  animation:blink 1.4s ease-in-out infinite}
.ship-dots span:nth-child(2){animation-delay:.2s}
.ship-dots span:nth-child(3){animation-delay:.4s}
@keyframes blink{0%,100%{opacity:.15}50%{opacity:.7}}
.ptrack{width:100%;height:2px;background:rgba(255,255,255,.07);border-radius:1px;
  position:relative;overflow:hidden}
.pdot{width:12px;height:12px;border-radius:50%;background:var(--red);position:absolute;
  top:-5px;animation:flow 2s linear infinite;box-shadow:0 0 10px var(--red),0 0 4px var(--red)}
.pconn:nth-child(2) .pdot{animation-delay:0s}
.pconn:nth-child(4) .pdot{animation-delay:.5s}
.pconn:nth-child(6) .pdot{animation-delay:1s}
.pconn:nth-child(8) .pdot{animation-delay:1.5s}
@keyframes flow{0%{left:-12px;opacity:0}10%{opacity:1}90%{opacity:1}100%{left:100%;opacity:0}}
.pconn-label{font-size:.6rem;color:var(--muted);text-align:center;line-height:1.3;white-space:nowrap}

/* stats bar */
.stats-bar{position:relative;z-index:2;display:flex;justify-content:center;gap:0;
  margin:0 52px;border-top:1px solid var(--glassborder);padding:10px 0;flex-shrink:0}
.stat{flex:1;text-align:center;padding:0 16px;border-right:1px solid var(--glassborder)}
.stat:last-child{border-right:none}
.stat-val{font-size:1.2rem;font-weight:800;color:var(--white);
  background:linear-gradient(90deg,var(--red),var(--orange));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.stat-key{font-size:.65rem;color:var(--muted);margin-top:1px;letter-spacing:.04em;text-transform:uppercase}

/* detail overlay */
.detail-overlay{
  position:fixed;inset:0;z-index:800;display:none;
  background:rgba(8,13,24,.75);backdrop-filter:blur(4px);
  align-items:center;justify-content:center}
.detail-overlay.show{display:flex}
.detail-modal{
  background:var(--bg2);border:1px solid var(--glassborder);
  border-top:3px solid var(--red);border-radius:18px;
  padding:32px 36px;max-width:600px;width:92%;
  box-shadow:0 24px 80px rgba(0,0,0,.6);
  animation:popIn .25s ease}
@keyframes popIn{from{opacity:0;transform:scale(.94)}to{opacity:1;transform:scale(1)}}
.dm-close{float:right;background:none;border:1px solid var(--glassborder);
  color:var(--muted);cursor:pointer;padding:3px 12px;border-radius:6px;
  font-size:.8rem;transition:.2s;margin-top:-4px}
.dm-close:hover{color:var(--red);border-color:var(--red)}
.dm-file{font-family:var(--mono);color:var(--teal);font-size:.8rem;margin-bottom:6px}
.dm-title{font-size:1.3rem;font-weight:800;color:var(--white);margin-bottom:16px}
.dm-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.dm-item{background:var(--glass);border:1px solid var(--glassborder);border-radius:8px;
  padding:10px 12px;font-size:.78rem;color:var(--text);line-height:1.4;position:relative;
  padding-left:22px}
.dm-item::before{content:'▸';color:var(--red);position:absolute;left:8px;top:11px;font-size:.65rem}

/* ════════════════════════════════════════════════════════
   SLIDE 2 — ANOMALY DETECTION
════════════════════════════════════════════════════════ */
#s2{background:var(--bg)}
#s2 .blob1{width:600px;height:600px;background:radial-gradient(circle,#1a0a30,transparent);top:-150px;right:-100px}
#s2 .blob2{width:400px;height:400px;background:radial-gradient(circle,#0d2a1a,transparent);bottom:-100px;left:5%}

.s2-inner{position:relative;z-index:2;display:flex;flex-direction:column;height:100%;padding:22px 40px 16px}

.s2-hero{flex-shrink:0;margin-bottom:16px}
.s2-title{font-size:2.2rem;font-weight:900;letter-spacing:-.01em}
.s2-title span{background:linear-gradient(90deg,var(--red),#ff6b6b);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.s2-sub{font-size:.85rem;color:var(--muted);margin-top:4px}

.s2-body{display:flex;gap:20px;flex:1;overflow:hidden}

/* anomaly cards grid */
.anomaly-grid{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;
  gap:12px;flex:1.15;overflow:hidden}

.acard{
  background:var(--glass);
  border:1px solid var(--glassborder);
  border-radius:14px;
  padding:16px 18px;
  cursor:pointer;
  display:flex;flex-direction:column;
  transition:transform .2s,box-shadow .2s,border-color .2s;
  position:relative;overflow:hidden;
  backdrop-filter:blur(10px)}
.acard::before{content:'';position:absolute;top:0;left:0;right:0;height:3px}
.acard.ca::before{background:linear-gradient(90deg,#e74c3c,#ff6b6b)}
.acard.cb::before{background:linear-gradient(90deg,#f39c12,#f1c40f)}
.acard.cc::before{background:linear-gradient(90deg,#17becf,#1abc9c)}
.acard.cd::before{background:linear-gradient(90deg,#9b59b6,#6c3483)}

.acard:hover{transform:translateY(-3px)}
.acard.ca:hover{box-shadow:0 8px 28px rgba(231,76,60,.2);border-color:#e74c3c}
.acard.cb:hover{box-shadow:0 8px 28px rgba(243,156,18,.2);border-color:#f39c12}
.acard.cc:hover{box-shadow:0 8px 28px rgba(23,190,207,.2);border-color:#17becf}
.acard.cd:hover{box-shadow:0 8px 28px rgba(155,89,182,.2);border-color:#9b59b6}

.acard-head{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.acard-icon{font-size:1.6rem;width:42px;height:42px;border-radius:10px;
  display:flex;align-items:center;justify-content:center;flex-shrink:0}
.ca .acard-icon{background:rgba(231,76,60,.12)}
.cb .acard-icon{background:rgba(243,156,18,.12)}
.cc .acard-icon{background:rgba(23,190,207,.12)}
.cd .acard-icon{background:rgba(155,89,182,.12)}

.acard-label{display:flex;flex-direction:column;gap:2px}
.acard-badge{font-size:.6rem;font-weight:800;letter-spacing:.1em;padding:2px 7px;
  border-radius:4px;display:inline-block;width:fit-content}
.ca .acard-badge{background:rgba(231,76,60,.15);color:#e74c3c}
.cb .acard-badge{background:rgba(243,156,18,.15);color:#f39c12}
.cc .acard-badge{background:rgba(23,190,207,.15);color:#17becf}
.cd .acard-badge{background:rgba(155,89,182,.15);color:#9b59b6}
.acard-name{font-size:.92rem;font-weight:700;color:var(--white)}

.acard-desc{font-size:.74rem;color:var(--muted);line-height:1.4;margin-bottom:10px;flex-shrink:0}

.acard-thresholds{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px}
.thresh{font-size:.64rem;padding:3px 8px;border-radius:5px;font-family:var(--mono);font-weight:600}
.ca .thresh{background:rgba(231,76,60,.1);color:#e74c3c;border:1px solid rgba(231,76,60,.2)}
.cb .thresh{background:rgba(243,156,18,.1);color:#f39c12;border:1px solid rgba(243,156,18,.2)}
.cc .thresh{background:rgba(23,190,207,.1);color:#17becf;border:1px solid rgba(23,190,207,.2)}
.cd .thresh{background:rgba(155,89,182,.1);color:#9b59b6;border:1px solid rgba(155,89,182,.2)}

.acard-facts{list-style:none;display:flex;flex-direction:column;gap:4px;flex:1;overflow:hidden}
.acard-facts li{font-size:.7rem;color:var(--text);padding-left:13px;
  position:relative;line-height:1.35;opacity:.85}
.acard-facts li::before{content:'▸';position:absolute;left:0;font-size:.6rem;top:1px}
.ca .acard-facts li::before{color:#e74c3c}
.cb .acard-facts li::before{color:#f39c12}
.cc .acard-facts li::before{color:#17becf}
.cd .acard-facts li::before{color:#9b59b6}

/* DFSI panel */
.dfsi-panel{
  flex:0.7;background:var(--glass);border:1px solid var(--glassborder);
  border-radius:16px;backdrop-filter:blur(12px);
  padding:22px 20px;display:flex;flex-direction:column;
  border-top:3px solid var(--red)}

.dfsi-panel h3{font-size:.7rem;color:var(--muted);letter-spacing:.1em;
  text-transform:uppercase;margin-bottom:4px}
.dfsi-panel h2{font-size:1.15rem;font-weight:800;color:var(--white);margin-bottom:4px}
.dfsi-tagline{font-size:.72rem;color:var(--muted);line-height:1.4;margin-bottom:16px;
  padding-bottom:14px;border-bottom:1px solid var(--glassborder)}

.dfsi-formula-display{font-family:var(--mono);font-size:.8rem;color:var(--muted);
  margin-bottom:20px;line-height:1.8}
.dfsi-formula-display .fh{color:var(--white);font-size:.95rem;font-weight:700}
.dfsi-formula-display .fc{color:var(--red)}

/* score bars */
.score-bars{display:flex;flex-direction:column;gap:12px;flex:1}
.sbar{display:flex;flex-direction:column;gap:5px}
.sbar-head{display:flex;justify-content:space-between;align-items:center}
.sbar-name{font-size:.72rem;font-weight:600;color:var(--white)}
.sbar-formula{font-family:var(--mono);font-size:.65rem}
.sbar-track{height:7px;background:rgba(255,255,255,.06);border-radius:4px;overflow:hidden}
.sbar-fill{height:100%;border-radius:4px;transform-origin:left;
  animation:barIn 1.2s cubic-bezier(.22,1,.36,1) both}
@keyframes barIn{from{transform:scaleX(0)}to{transform:scaleX(1)}}
.sbar:nth-child(1) .sbar-fill{background:linear-gradient(90deg,#e74c3c,#ff6b6b);width:55%;animation-delay:.3s}
.sbar:nth-child(2) .sbar-fill{background:linear-gradient(90deg,#2ecc71,#1abc9c);width:78%;animation-delay:.5s}
.sbar:nth-child(3) .sbar-fill{background:linear-gradient(90deg,#17becf,#3498db);width:100%;animation-delay:.7s}
.sbar-sub{font-size:.64rem;color:var(--muted);line-height:1.3}

.dfsi-note{margin-top:auto;padding-top:14px;border-top:1px solid var(--glassborder);
  font-size:.68rem;color:var(--muted);line-height:1.5}
.dfsi-note strong{color:var(--text)}

/* ════════════════════════════════════════════════════════
   SLIDES 3-5 — MAPS
════════════════════════════════════════════════════════ */
.map-slide{background:var(--bg)}
.map-bar{
  height:62px;display:flex;align-items:center;justify-content:space-between;
  padding:0 28px;background:var(--bg2);
  border-bottom:2px solid rgba(231,76,60,.4);flex-shrink:0;position:relative;z-index:5}
.map-bar-l h2{font-size:1.05rem;font-weight:700;color:var(--white)}
.map-bar-l p{font-size:.73rem;color:var(--muted);margin-top:1px}
.mbadge{font-size:.67rem;padding:3px 11px;border-radius:14px;font-weight:700;
  letter-spacing:.04em;border:1px solid transparent}
.mbadge-r{background:rgba(231,76,60,.12);color:#e74c3c;border-color:rgba(231,76,60,.25)}
.mbadge-b{background:rgba(31,119,180,.12);color:#1f77b4;border-color:rgba(31,119,180,.25)}
.mbadge-p{background:rgba(148,103,189,.12);color:#9467bd;border-color:rgba(148,103,189,.25)}
.map-iframe-wrap{flex:1;position:relative}
.map-iframe-wrap iframe{width:100%;height:100%;border:none;display:block}

/* scrollbar */
::-webkit-scrollbar{width:5px;background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--bg3);border-radius:3px}
</style>
</head>
<body>

<nav class="dots" id="dots">
  <a href="#s1" title="Pipeline"></a>
  <a href="#s2" title="Anomalies"></a>
  <a href="#s3" title="Going Dark"></a>
  <a href="#s4" title="D1 Map"></a>
  <a href="#s5" title="D2 Map"></a>
</nav>

<div class="deck" id="deck">

<!-- ════════════════════════════════════════════════════
     SLIDE 1 — THE BIG DATA PIPELINE
════════════════════════════════════════════════════ -->
<section class="slide" id="s1">
  <canvas class="bg-canvas" id="c1"></canvas>
  <div class="blob blob1"></div>
  <div class="blob blob2"></div>

  <div class="s1-hero">
    <div class="s1-hero-top">
      <div>
        <div class="s1-title">The <span>Big Data</span> Pipeline</div>
        <div class="s1-sub">Multi-gigabyte AIS CSV files streamed row-by-row via Python generators, cleaned, chunked, and processed in parallel across CPU workers — without ever loading the full file into memory</div>
      </div>
      <div class="s1-hint">Click any component for details</div>
    </div>
    <div class="divider"></div>
  </div>

  <div class="pipeline" id="pipeline">

    <!-- reader.py -->
    <div class="pnode" data-key="reader">
      <div class="pcard">
        <div class="pcard-top-bar"></div>
        <div class="picon">📡</div>
        <div class="pfile">reader.py</div>
        <div class="ptitle">Streaming Layer</div>
        <ul class="pfacts">
          <li>Reads header once → O(1) column lookup</li>
          <li>Yields 7 fields from ~50 columns per row</li>
          <li>Chains 2 CSV files into one continuous stream</li>
          <li>Assigns global chunk_id for ordered merging</li>
          <li>10 GB file uses same RAM as one chunk</li>
        </ul>
        <div class="pmore">click to explore</div>
      </div>
    </div>

    <div class="pconn">
      <div class="ptrack"><div class="pdot"></div></div>
      <div class="pconn-label">raw rows<br>streaming</div>
    </div>

    <!-- parser.py -->
    <div class="pnode" data-key="parser">
      <div class="pcard">
        <div class="pcard-top-bar"></div>
        <div class="picon">🧹</div>
        <div class="pfile">parser.py</div>
        <div class="ptitle">Cleaning Layer</div>
        <ul class="pfacts">
          <li>Runs inside each worker process</li>
          <li>Class A vessels only — drops buoys, aircraft</li>
          <li>Validates MMSI: 9-digit, no placeholders</li>
          <li>Lat/lon range check, rejects (0,0) coords</li>
          <li>Cheapest filter runs first → fail fast</li>
        </ul>
        <div class="pmore">click to explore</div>
      </div>
    </div>

    <div class="pconn">
      <div class="ptrack"><div class="pdot"></div></div>
      <div class="pconn-label">clean chunks<br>dispatched</div>
    </div>

    <!-- worker_pool.py -->
    <div class="pnode" data-key="worker">
      <div class="pcard">
        <div class="pcard-top-bar"></div>
        <div class="picon">⚙️</div>
        <div class="pfile">worker_pool.py</div>
        <div class="ptitle">Parallel Workers</div>
        <ul class="pfacts">
          <li>Pool.imap_unordered — N cores in parallel</li>
          <li>Workers init once: PORT_ZONES + ROW_PARSER</li>
          <li>Groups by MMSI, sorts by timestamp</li>
          <li>Downsamples to 5-min for anomalies A & C</li>
          <li>Detects A, B, C, D1, D2 per chunk</li>
        </ul>
        <div class="pmore">click to explore</div>
      </div>
    </div>

    <div class="pconn">
      <div class="ptrack"><div class="pdot"></div></div>
      <div class="pconn-label">chunk results<br>out-of-order</div>
    </div>

    <!-- merge.py -->
    <div class="pnode" data-key="merge">
      <div class="pcard">
        <div class="pcard-top-bar"></div>
        <div class="picon">🔗</div>
        <div class="pfile">merge.py</div>
        <div class="ptitle">Merge Layer</div>
        <ul class="pfacts">
          <li>Buffers results, reassembles by chunk_id</li>
          <li>Compares boundary: last of chunk N vs first of N+1</li>
          <li>Catches anomalies spanning chunk boundaries</li>
          <li>A & C use sampled records; D uses full-res</li>
          <li>D1 and D2 tracked separately</li>
        </ul>
        <div class="pmore">click to explore</div>
      </div>
    </div>

    <div class="pconn">
      <div class="ptrack"><div class="pdot"></div></div>
      <div class="pconn-label">global events<br>all vessels</div>
    </div>

    <!-- run_detection.py -->
    <div class="pnode" data-key="scoring">
      <div class="pcard">
        <div class="pcard-top-bar"></div>
        <div class="picon">🏆</div>
        <div class="pfile">run_detection.py</div>
        <div class="ptitle">Scoring & Output</div>
        <ul class="pfacts">
          <li>Aggregates all events per vessel</li>
          <li>Computes DFSI score for every MMSI</li>
          <li>Ranks vessels by suspicion descending</li>
          <li>Writes dfsi_results.csv + map CSVs</li>
          <li>MemoryMonitor logs RAM throughout</li>
        </ul>
        <div class="pmore">click to explore</div>
      </div>
    </div>

  </div><!-- /pipeline -->

  <!-- floating ship -->
  <div class="ship-lane">
    <div class="wave-strip"></div>
    <div class="ship-float">
      <div class="ship-dots"><span></span><span></span><span></span></div>
      <div class="ship-svg">&#x1F6A2;</div>
      <div class="ship-label">Big&nbsp;Data</div>
      <div class="ship-dots"><span></span><span></span><span></span></div>
    </div>
  </div>

  <div class="stats-bar">
    <div class="stat"><div class="stat-val">2</div><div class="stat-key">CSV input files</div></div>
    <div class="stat"><div class="stat-val">7 / ~50</div><div class="stat-key">columns kept per row</div></div>
    <div class="stat"><div class="stat-val">5-min</div><div class="stat-key">downsample interval A&C</div></div>
    <div class="stat"><div class="stat-val">60 kn</div><div class="stat-key">teleportation threshold</div></div>
    <div class="stat"><div class="stat-val">4h / 1km</div><div class="stat-key">going dark threshold</div></div>
    <div class="stat"><div class="stat-val">DFSI</div><div class="stat-key">final vessel ranking</div></div>
  </div>

</section>

<!-- detail overlay -->
<div class="detail-overlay" id="detailOverlay">
  <div class="detail-modal">
    <button class="dm-close" onclick="closeDetail()">close ✕</button>
    <div class="dm-file" id="dmFile"></div>
    <div class="dm-title" id="dmTitle"></div>
    <div class="dm-grid" id="dmGrid"></div>
  </div>
</div>


<!-- ════════════════════════════════════════════════════
     SLIDE 2 — ANOMALY DETECTION
════════════════════════════════════════════════════ -->
<section class="slide" id="s2">
  <canvas class="bg-canvas" id="c2"></canvas>
  <div class="blob blob1"></div>
  <div class="blob blob2"></div>

  <div class="s2-inner">
    <div class="s2-hero">
      <div class="s2-title"><span>Anomaly</span> Detection Engine</div>
      <div class="s2-sub">Four suspicious behaviours detected in <code style="color:var(--teal);font-family:var(--mono)">rules.py</code> — every consecutive AIS ping pair checked against all rules simultaneously</div>
    </div>

    <div class="s2-body">

      <!-- 2x2 anomaly cards -->
      <div class="anomaly-grid">

        <!-- A -->
        <div class="acard ca">
          <div class="acard-head">
            <div class="acard-icon">🌑</div>
            <div class="acard-label">
              <div class="acard-badge">ANOMALY A</div>
              <div class="acard-name">Going Dark</div>
            </div>
          </div>
          <div class="acard-desc">Vessel disables AIS transponder while continuing to move — conceals route, port calls, and cargo activity from authorities and tracking systems.</div>
          <div class="acard-thresholds">
            <span class="thresh">gap &gt; 4 hours</span>
            <span class="thresh">distance &gt; 1 km</span>
            <span class="thresh">haversine dist</span>
          </div>
          <ul class="acard-facts">
            <li>Detected by <code style="font-family:var(--mono);font-size:.65rem">detect_going_dark()</code> in rules.py</li>
            <li>Stationary vessels excluded — movement required</li>
            <li>Runs on 5-min downsampled records</li>
            <li>DFSI contribution: <code style="font-family:var(--mono);font-size:.65rem">max_gap_hours / 2</code></li>
          </ul>
        </div>

        <!-- B -->
        <div class="acard cb">
          <div class="acard-head">
            <div class="acard-icon">🤝</div>
            <div class="acard-label">
              <div class="acard-badge">ANOMALY B</div>
              <div class="acard-name">Loitering &amp; Transfer</div>
            </div>
          </div>
          <div class="acard-desc">Two vessels linger together at sea at very low speed — indicates covert ship-to-ship transfer of cargo, fuel, or sanctioned goods outside port oversight.</div>
          <div class="acard-thresholds">
            <span class="thresh">proximity &lt; 0.5 km</span>
            <span class="thresh">SOG &lt; 1 kn</span>
            <span class="thresh">duration &ge; 2h</span>
          </div>
          <ul class="acard-facts">
            <li>Detected via <code style="font-family:var(--mono);font-size:.65rem">detect_loitering_transfers()</code></li>
            <li>Spatial grid bucketing for fast proximity search</li>
            <li>Outside port zones only — port visits excluded</li>
            <li>Runs post-merge on globally merged sampled records</li>
          </ul>
        </div>

        <!-- C -->
        <div class="acard cc">
          <div class="acard-head">
            <div class="acard-icon">⚓</div>
            <div class="acard-label">
              <div class="acard-badge">ANOMALY C</div>
              <div class="acard-name">Draft Change</div>
            </div>
          </div>
          <div class="acard-desc">Ship draught changes significantly during an AIS blackout while at sea — strongly suggests covert loading or unloading of cargo away from port inspection.</div>
          <div class="acard-thresholds">
            <span class="thresh">gap &gt; 2 hours</span>
            <span class="thresh">draught &Delta; &gt; 5%</span>
            <span class="thresh">at sea only</span>
          </div>
          <ul class="acard-facts">
            <li>Detected via <code style="font-family:var(--mono);font-size:.65rem">detect_draft_change()</code></li>
            <li>Vessel must be outside all port zone polygons</li>
            <li>Hardest anomaly to explain innocently</li>
            <li>DFSI contribution: <code style="font-family:var(--mono);font-size:.65rem">count &times; 15</code> — highest weight</li>
          </ul>
        </div>

        <!-- D -->
        <div class="acard cd">
          <div class="acard-head">
            <div class="acard-icon">👥</div>
            <div class="acard-label">
              <div class="acard-badge">ANOMALY D</div>
              <div class="acard-name">Teleportation / Cloning</div>
            </div>
          </div>
          <div class="acard-desc">Same MMSI broadcasts from two physically impossible locations — reveals identity cloning where a shadow vessel spoofs a legitimate ship's AIS identity.</div>
          <div class="acard-thresholds">
            <span class="thresh">speed &gt; 60 kn</span>
            <span class="thresh">D1: gap &le; 30 min</span>
            <span class="thresh">D2: 30 min–24h</span>
          </div>
          <ul class="acard-facts">
            <li><strong>D1</strong> — near-simultaneous: two ships, one MMSI at same time</li>
            <li><strong>D2</strong> — impossible relocation after a longer AIS gap</li>
            <li>Rejects (0,0) coordinates and gaps &lt; 30 seconds</li>
            <li>D2 DFSI: <code style="font-family:var(--mono);font-size:.65rem">total_D2_jump_nm / 10</code></li>
          </ul>
        </div>

      </div><!-- /anomaly-grid -->

      <!-- DFSI panel -->
      <div class="dfsi-panel">
        <h3>Suspicion Scoring</h3>
        <h2>Dark Fleet Suspicion Index</h2>
        <div class="dfsi-tagline">Every vessel receives a DFSI score aggregating evidence from all detected anomalies. Higher score = more suspicious. Output ranked in <code style="font-family:var(--mono);font-size:.68rem;color:var(--teal)">dfsi_results.csv</code></div>

        <div class="dfsi-formula-display">
          <div class="fh">DFSI =</div>
          <div>&nbsp;&nbsp;<span class="fc">max_gap_h</span> / 2</div>
          <div>&nbsp;&nbsp;+ <span class="fc">D2_jump_nm</span> / 10</div>
          <div>&nbsp;&nbsp;+ <span class="fc">draft_count</span> &times; 15</div>
        </div>

        <div class="score-bars">
          <div class="sbar">
            <div class="sbar-head">
              <div class="sbar-name">Anomaly A — Going Dark</div>
              <div class="sbar-formula" style="color:#e74c3c">max_gap_h / 2</div>
            </div>
            <div class="sbar-track"><div class="sbar-fill"></div></div>
            <div class="sbar-sub">Proportional to worst single blackout duration. A 10h blackout scores 5 points.</div>
          </div>
          <div class="sbar">
            <div class="sbar-head">
              <div class="sbar-name">Anomaly D2 — Teleportation</div>
              <div class="sbar-formula" style="color:#2ecc71">D2_jump_nm / 10</div>
            </div>
            <div class="sbar-track"><div class="sbar-fill"></div></div>
            <div class="sbar-sub">Cumulative impossible jump distance. Only D2 counts — D1 is identity cloning not relocation.</div>
          </div>
          <div class="sbar">
            <div class="sbar-head">
              <div class="sbar-name">Anomaly C — Draft Change</div>
              <div class="sbar-formula" style="color:#17becf">count &times; 15</div>
            </div>
            <div class="sbar-track"><div class="sbar-fill"></div></div>
            <div class="sbar-sub">Highest weight — each covert cargo op scores 15 points. Very hard to explain innocently.</div>
          </div>
        </div>

        <div class="dfsi-note">
          <strong>Output files:</strong> dfsi_results.csv (all vessels ranked) &middot; top_going_dark_vessel_map.csv &middot; top_teleportation_d1/d2_vessel_map.csv &middot; memory_profile.csv
        </div>
      </div><!-- /dfsi-panel -->

    </div><!-- /s2-body -->
  </div><!-- /s2-inner -->
</section>


<!-- ════════════════════════════════════════════════════
     SLIDE 3 — GOING DARK MAP
════════════════════════════════════════════════════ -->
<section class="slide map-slide" id="s3">
  <div class="map-bar">
    <div class="map-bar-l">
      <h2>🌑 Anomaly A — Going Dark</h2>
      <p>Blue = last known position &nbsp;·&nbsp; Red = reappearance &nbsp;·&nbsp; Orange line = AIS blackout gap</p>
    </div>
    <div style="display:flex;gap:8px">
      <span class="mbadge mbadge-r">Gap &gt; 4h</span>
      <span class="mbadge mbadge-r">Distance &gt; 1km</span>
    </div>
  </div>
  <div class="map-iframe-wrap">
    <iframe srcdoc="%%GOING_DARK%%" sandbox="allow-scripts allow-same-origin"></iframe>
  </div>
</section>


<!-- ════════════════════════════════════════════════════
     SLIDE 4 — D1 TELEPORTATION
════════════════════════════════════════════════════ -->
<section class="slide map-slide" id="s4">
  <div class="map-bar">
    <div class="map-bar-l">
      <h2>👥 Anomaly D1 — Near-Simultaneous Identity Cloning</h2>
      <p>Blue = Vessel A (southern cluster) &nbsp;·&nbsp; Orange = Vessel B (northern cluster) &nbsp;·&nbsp; Dashed = same MMSI, same time, two locations</p>
    </div>
    <div style="display:flex;gap:8px">
      <span class="mbadge mbadge-b">Gap &le; 30 min</span>
      <span class="mbadge mbadge-b">Speed &gt; 60 kn</span>
    </div>
  </div>
  <div class="map-iframe-wrap">
    <iframe srcdoc="%%TELE_D1%%" sandbox="allow-scripts allow-same-origin"></iframe>
  </div>
</section>


<!-- ════════════════════════════════════════════════════
     SLIDE 5 — D2 TELEPORTATION
════════════════════════════════════════════════════ -->
<section class="slide map-slide" id="s5">
  <div class="map-bar">
    <div class="map-bar-l">
      <h2>🚀 Anomaly D2 — Impossible Relocation</h2>
      <p>Cyan = last known position &nbsp;·&nbsp; Orange = reappearance &nbsp;·&nbsp; Purple line = impossible jump (30 min to 24h gap)</p>
    </div>
    <div style="display:flex;gap:8px">
      <span class="mbadge mbadge-p">30 min – 24h</span>
      <span class="mbadge mbadge-p">Speed &gt; 60 kn</span>
    </div>
  </div>
  <div class="map-iframe-wrap">
    <iframe srcdoc="%%TELE_D2%%" sandbox="allow-scripts allow-same-origin"></iframe>
  </div>
</section>

</div><!-- /deck -->

<script>
/* ── Canvas particle network ─────────────────────────── */
function initCanvas(id) {
  const canvas = document.getElementById(id);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let W, H, pts;

  function resize() {
    W = canvas.width  = canvas.offsetWidth;
    H = canvas.height = canvas.offsetHeight;
    pts = Array.from({length: 55}, () => ({
      x: Math.random() * W, y: Math.random() * H,
      vx: (Math.random() - .5) * .4, vy: (Math.random() - .5) * .4,
      r: Math.random() * 1.5 + .5
    }));
  }
  resize();
  window.addEventListener('resize', resize);

  function draw() {
    ctx.clearRect(0, 0, W, H);
    pts.forEach(p => {
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0 || p.x > W) p.vx *= -1;
      if (p.y < 0 || p.y > H) p.vy *= -1;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(180,50,40,.35)';
      ctx.fill();
    });
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y;
        const d = Math.sqrt(dx*dx + dy*dy);
        if (d < 130) {
          ctx.beginPath();
          ctx.moveTo(pts[i].x, pts[i].y);
          ctx.lineTo(pts[j].x, pts[j].y);
          ctx.strokeStyle = `rgba(180,50,40,${(1 - d/130) * .12})`;
          ctx.lineWidth = .8;
          ctx.stroke();
        }
      }
    }
    requestAnimationFrame(draw);
  }
  draw();
}
initCanvas('c1');
initCanvas('c2');

/* ── Dot nav ─────────────────────────────────────────── */
const deck  = document.getElementById('deck');
const dots  = document.querySelectorAll('.dots a');
const slides = document.querySelectorAll('.slide');

const io = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      dots.forEach(d => d.classList.remove('on'));
      const i = [...slides].indexOf(e.target);
      if (dots[i]) dots[i].classList.add('on');
    }
  });
}, { root: deck, threshold: .5 });
slides.forEach(s => io.observe(s));

dots.forEach(d => d.addEventListener('click', e => {
  e.preventDefault();
  const t = document.querySelector(d.getAttribute('href'));
  deck.scrollTo({ top: t.offsetTop, behavior: 'smooth' });
}));

/* ── Pipeline detail overlay ─────────────────────────── */
const DETAILS = {
  reader: {
    file: 'src/streaming/reader.py',
    title: 'Streaming Layer — How data enters the pipeline',
    points: [
      'Opens each CSV file and reads the header row exactly once',
      'build_raw_row_column_indices() maps column names to indices for O(1) access',
      'stream_raw_rows() is a generator — yields one row at a time, never buffers the file',
      'Extracts only 7 fields from ~50 columns: timestamp, MMSI, lat, lon, SOG, draught, vessel class',
      'stream_raw_rows_from_files() chains both input CSVs using yield from — two files appear as one feed',
      'stream_csv_files_in_chunks() accumulates N rows into a list and assigns a global chunk_id',
      'chunk_id is critical — used later by merge.py to reassemble results in the correct order',
      'Memory footprint: only one chunk lives in RAM at any time regardless of file size',
    ]
  },
  parser: {
    file: 'src/streaming/parser.py',
    title: 'Cleaning Layer — Filter chain validation',
    points: [
      'Runs inside each worker process, initialized once per worker via worker_init()',
      'AISRowParser.parse_row() applies filters from cheapest to most expensive',
      'Filter 1 — Vessel class: keep only Class A (commercial vessels); drops buoys, aircraft, coast stations',
      'Filter 2 — Timestamp: must be parseable as UTC datetime; malformed strings dropped',
      'Filter 3 — MMSI: must be exactly 9 digits; rejects placeholders like 000000000 or 111111111',
      'Filter 4 — Coordinates: lat in [-90,90], lon in [-180,180]; rejects exact (0,0) placeholder',
      'Filter 5 — SOG & draught: parsed as float if present; missing values allowed (not required)',
      'Row dropped on first failure — invalid rows never reach anomaly detection logic',
    ]
  },
  worker: {
    file: 'src/parallel/worker_pool.py',
    title: 'Parallel Workers — Anomaly detection per chunk',
    points: [
      'Uses multiprocessing.Pool.imap_unordered — chunks dispatched to workers as they arrive',
      'Worker processes initialized once via worker_init() — PORT_ZONES and ROW_PARSER loaded as globals',
      'process_chunk() receives a raw chunk, parses rows, groups by MMSI, sorts each vessel by timestamp',
      '_downsample_records() reduces to 5-minute intervals for anomalies A & C (reduces noise)',
      'Full-resolution records used for anomaly D — downsampling would hide teleportation signals',
      'Runs detect_going_dark(), detect_draft_change(), detect_teleportation() on every consecutive pair',
      'Teleportation classified: gap <= 30min → D1 (cloning); 30min-24h → D2 (impossible relocation)',
      'Saves boundary records (first + last ping per vessel per chunk) for cross-chunk analysis in merge.py',
    ]
  },
  merge: {
    file: 'src/anomaly_detection/merge.py',
    title: 'Merge Layer — Cross-chunk boundary stitching',
    points: [
      'Workers return results out of order — merge layer uses a pending buffer keyed by chunk_id',
      'Results processed strictly in chunk_id order using next_chunk_id_to_merge counter',
      'BoundaryState stores last_record and last_sampled_record per MMSI from the previous chunk',
      'For each new chunk, compares boundary: last record of chunk N vs first record of chunk N+1',
      'This catches anomalies that span a chunk boundary — no single worker ever sees both sides',
      'A & C boundary checks use sampled records (5-min intervals); D uses full-resolution records',
      'D1 and D2 boundary events tracked in separate lists on VesselGlobalSummary',
      'Anomaly B (loitering) runs post-merge on globally aggregated sampled records — needs global view',
    ]
  },
  scoring: {
    file: 'scripts/run_detection.py',
    title: 'Scoring & Output — DFSI ranking and CSV export',
    points: [
      'Collects VesselGlobalSummary objects from all chunks after merge completes',
      'DFSI = max_gap_hours/2 + total_D2_jump_nm/10 + draft_change_count×15',
      'Only D2 contributes to DFSI — D1 (identity cloning) tracked separately',
      'All vessels sorted by DFSI descending — highest score = most suspicious',
      'Writes dfsi_results.csv with full anomaly breakdown per vessel',
      'Extracts top vessel coordinates for each anomaly type into map CSVs',
      'MemoryMonitor background thread samples RAM every second → memory_profile.csv',
      'Supports --enable-loitering-detection flag to include anomaly B processing',
    ]
  }
};

function openDetail(key) {
  const d = DETAILS[key];
  document.getElementById('dmFile').textContent  = d.file;
  document.getElementById('dmTitle').textContent = d.title;
  document.getElementById('dmGrid').innerHTML = d.points
    .map(p => `<div class="dm-item">${p}</div>`).join('');
  document.getElementById('detailOverlay').classList.add('show');
  document.querySelectorAll('.pnode').forEach(n => n.classList.remove('lit'));
  document.querySelector(`[data-key="${key}"]`).classList.add('lit');
}
function closeDetail() {
  document.getElementById('detailOverlay').classList.remove('show');
  document.querySelectorAll('.pnode').forEach(n => n.classList.remove('lit'));
}
document.getElementById('detailOverlay').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeDetail();
});
document.querySelectorAll('.pnode').forEach(n => {
  n.addEventListener('click', () => openDetail(n.dataset.key));
});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    build()