"""Interactive treemap visualization for git-who.

Generates a self-contained HTML file with a zoomable treemap showing
code ownership and risk. Files are sized by activity (commits × lines)
and colored by bus factor risk. Click directories to zoom, click
breadcrumb to zoom out.
"""

from __future__ import annotations

import html
import json
from collections import defaultdict
from pathlib import PurePosixPath

from .analyzer import RepoAnalysis


def _build_tree(analysis: RepoAnalysis) -> dict:
    """Convert flat file analysis into a hierarchical tree for the treemap."""
    root: dict = {"name": "/", "children": {}}

    for filepath, ownership in analysis.files.items():
        parts = PurePosixPath(filepath).parts
        node = root
        for part in parts[:-1]:
            if part not in node["children"]:
                node["children"][part] = {"name": part, "children": {}}
            node = node["children"][part]

        filename = parts[-1] if parts else filepath
        total_commits = sum(e.commits for e in ownership.experts)
        total_lines = sum(e.lines_added + e.lines_deleted for e in ownership.experts)
        # Activity metric: sqrt(commits * lines) to balance both
        activity = max(1, int((total_commits * max(1, total_lines)) ** 0.5))

        experts_list = [
            {"name": e.author, "score": round(e.score, 1), "commits": e.commits}
            for e in ownership.experts[:5]
        ]

        node["children"][filename] = {
            "name": filename,
            "value": activity,
            "bus_factor": ownership.bus_factor,
            "commits": total_commits,
            "lines": total_lines,
            "experts": experts_list,
            "path": filepath,
        }

    def _convert(node: dict) -> dict:
        """Convert dict-of-dicts to list-of-children format, rolling up sizes."""
        if "value" in node:
            return node  # leaf
        children = [_convert(c) for c in node["children"].values()]
        children.sort(key=lambda c: c.get("value", 0) or sum(
            x.get("value", 0) for x in c.get("children", [])
        ), reverse=True)
        result = {"name": node["name"], "children": children}
        return result

    tree = _convert(root)
    return tree


def generate_treemap_html(analysis: RepoAnalysis) -> str:
    """Generate a self-contained interactive treemap HTML page."""
    tree_data = _build_tree(analysis)
    tree_json = json.dumps(tree_data)
    repo_name = analysis.path.rstrip("/").split("/")[-1]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>git-who map — {html.escape(repo_name)}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  background: #0a0e1a; color: #e2e8f0; overflow: hidden; height: 100vh;
}}
#header {{
  background: linear-gradient(135deg, #0f172a 0%, #1a1f3a 100%);
  border-bottom: 1px solid #334155;
  padding: 12px 20px; display: flex; align-items: center; gap: 16px;
  justify-content: space-between; flex-wrap: wrap;
}}
#header h1 {{ font-size: 18px; font-weight: 700; white-space: nowrap; }}
#header h1 span {{ color: #3b82f6; }}
#breadcrumb {{
  display: flex; align-items: center; gap: 4px; font-size: 13px;
  color: #94a3b8; flex: 1; min-width: 200px;
}}
#breadcrumb .crumb {{
  cursor: pointer; padding: 2px 8px; border-radius: 4px;
  transition: all 0.15s;
}}
#breadcrumb .crumb:hover {{ background: #1e293b; color: #e2e8f0; }}
#breadcrumb .crumb.active {{ color: #e2e8f0; font-weight: 600; }}
#breadcrumb .sep {{ color: #475569; }}
#legend {{
  display: flex; gap: 12px; align-items: center; font-size: 12px;
  color: #94a3b8;
}}
.legend-item {{
  display: flex; align-items: center; gap: 4px;
}}
.legend-dot {{
  width: 10px; height: 10px; border-radius: 2px;
}}
#stats {{
  display: flex; gap: 16px; font-size: 12px; color: #94a3b8;
}}
.stat-val {{ font-weight: 700; color: #e2e8f0; }}
#container {{
  position: relative; width: 100vw;
  height: calc(100vh - 52px);
  overflow: hidden;
}}
.node {{
  position: absolute; overflow: hidden;
  transition: all 0.4s cubic-bezier(0.25, 0.1, 0.25, 1);
  cursor: pointer;
}}
.node-leaf {{
  border: 1px solid rgba(0,0,0,0.3);
}}
.node-leaf:hover {{
  border-color: #3b82f6;
  z-index: 10;
  filter: brightness(1.2);
}}
.node-dir {{
  border: 2px solid rgba(255,255,255,0.08);
  background: rgba(0,0,0,0.15);
}}
.node-label {{
  position: absolute; left: 4px; top: 2px;
  font-size: 11px; color: rgba(255,255,255,0.85);
  text-shadow: 0 1px 2px rgba(0,0,0,0.8);
  pointer-events: none; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
  max-width: calc(100% - 8px);
  font-weight: 500;
}}
.node-dir > .node-label {{
  font-size: 12px; font-weight: 700;
  color: rgba(255,255,255,0.6);
  text-transform: uppercase; letter-spacing: 0.5px;
}}
.node-score {{
  position: absolute; right: 4px; bottom: 2px;
  font-size: 10px; color: rgba(255,255,255,0.5);
  pointer-events: none;
}}
#tooltip {{
  position: fixed; display: none; pointer-events: none;
  background: #1e293b; border: 1px solid #475569;
  border-radius: 8px; padding: 12px 16px;
  font-size: 13px; max-width: 320px; z-index: 1000;
  box-shadow: 0 8px 32px rgba(0,0,0,0.5);
}}
#tooltip .tt-path {{
  font-family: 'SF Mono', monospace; font-size: 12px;
  color: #3b82f6; margin-bottom: 8px; word-break: break-all;
}}
#tooltip .tt-row {{
  display: flex; justify-content: space-between; gap: 12px;
  margin: 2px 0; color: #94a3b8;
}}
#tooltip .tt-val {{ color: #e2e8f0; font-weight: 600; }}
#tooltip .tt-bf {{ font-size: 14px; font-weight: 700; margin: 6px 0 4px; }}
#tooltip .tt-experts {{ margin-top: 8px; border-top: 1px solid #334155; padding-top: 6px; }}
#tooltip .tt-expert {{
  display: flex; justify-content: space-between; gap: 8px;
  font-size: 12px; margin: 2px 0;
}}
#tooltip .tt-expert .name {{ color: #e2e8f0; }}
#tooltip .tt-expert .score {{ color: #94a3b8; }}
.bf-1 {{ color: #ef4444; }}
.bf-2 {{ color: #f97316; }}
.bf-3 {{ color: #eab308; }}
.bf-ok {{ color: #22c55e; }}
</style>
</head>
<body>

<div id="header">
  <h1><span>git-who</span> map</h1>
  <div id="breadcrumb"><span class="crumb active">{html.escape(repo_name)}</span></div>
  <div id="stats"></div>
  <div id="legend">
    <span style="color:#64748b">Risk:</span>
    <div class="legend-item"><div class="legend-dot" style="background:#ef4444"></div>Bus factor 1</div>
    <div class="legend-item"><div class="legend-dot" style="background:#f97316"></div>2</div>
    <div class="legend-item"><div class="legend-dot" style="background:#eab308"></div>3</div>
    <div class="legend-item"><div class="legend-dot" style="background:#22c55e"></div>4+</div>
  </div>
</div>

<div id="container"></div>
<div id="tooltip"></div>

<script>
const DATA = {tree_json};
const REPO_NAME = {json.dumps(repo_name)};

// Colors by bus factor
function bfColor(bf) {{
  if (bf <= 1) return '#b91c1c';     // dark red
  if (bf === 2) return '#c2410c';    // dark orange
  if (bf === 3) return '#a16207';    // dark yellow
  return '#15803d';                   // dark green
}}
function bfBg(bf) {{
  if (bf <= 1) return 'linear-gradient(135deg, #991b1b 0%, #7f1d1d 100%)';
  if (bf === 2) return 'linear-gradient(135deg, #9a3412 0%, #7c2d12 100%)';
  if (bf === 3) return 'linear-gradient(135deg, #854d0e 0%, #713f12 100%)';
  return 'linear-gradient(135deg, #166534 0%, #14532d 100%)';
}}
function bfClass(bf) {{
  if (bf <= 1) return 'bf-1';
  if (bf === 2) return 'bf-2';
  if (bf === 3) return 'bf-3';
  return 'bf-ok';
}}

// Squarified treemap layout
function sumValues(node) {{
  if (node.value != null) return node.value;
  if (!node.children) return 0;
  let s = 0;
  for (const c of node.children) s += sumValues(c);
  node._total = s;
  return s;
}}

function layoutTreemap(node, x, y, w, h) {{
  node._x = x; node._y = y; node._w = w; node._h = h;
  if (!node.children || node.children.length === 0) return;

  const total = node._total || sumValues(node);
  if (total === 0) return;

  // Sort children by value descending
  const sorted = node.children.slice().sort(
    (a, b) => (b._total || b.value || 0) - (a._total || a.value || 0)
  );

  squarify(sorted, x, y, w, h, total);
}}

function squarify(items, x, y, w, h, total) {{
  if (items.length === 0) return;
  if (items.length === 1) {{
    layoutTreemap(items[0], x, y, w, h);
    return;
  }}

  const PAD = 2;  // padding between items

  // Slice-and-dice with squarification
  let vertical = w >= h;
  let remaining = [...items];
  let cx = x, cy = y, cw = w, ch = h;
  let rTotal = total;

  while (remaining.length > 0) {{
    vertical = cw >= ch;
    let row = [remaining[0]];
    let rowTotal = (remaining[0]._total || remaining[0].value || 0);
    remaining.splice(0, 1);

    let bestAspect = Infinity;

    while (remaining.length > 0) {{
      const next = remaining[0];
      const nextVal = (next._total || next.value || 0);
      const newRowTotal = rowTotal + nextVal;

      // Calculate aspect ratios
      const frac = newRowTotal / rTotal;
      const rowLen = vertical ? ch * frac : cw * frac;
      const crossLen = vertical ? cw : ch;

      let worstAspect = 0;
      for (const item of [...row, next]) {{
        const itemVal = (item._total || item.value || 0);
        const itemFrac = itemVal / newRowTotal;
        const itemLen = crossLen * itemFrac;
        const aspect = Math.max(rowLen / Math.max(1, itemLen), itemLen / Math.max(1, rowLen));
        worstAspect = Math.max(worstAspect, aspect);
      }}

      if (worstAspect > bestAspect && row.length > 0) break;

      bestAspect = worstAspect;
      row.push(next);
      rowTotal += nextVal;
      remaining.splice(0, 1);
    }}

    // Layout this row
    const frac = rTotal > 0 ? rowTotal / rTotal : 0;
    let rx, ry, rw, rh;
    if (vertical) {{
      rw = cw; rh = ch * frac;
      rx = cx; ry = cy;
      cy += rh; ch -= rh;
    }} else {{
      rw = cw * frac; rh = ch;
      rx = cx; ry = cy;
      cx += rw; cw -= rw;
    }}

    // Layout items in this row
    let offset = 0;
    for (const item of row) {{
      const itemVal = (item._total || item.value || 0);
      const itemFrac = rowTotal > 0 ? itemVal / rowTotal : 0;
      let ix, iy, iw, ih;
      if (vertical) {{
        ix = rx + offset; iy = ry;
        iw = rw * itemFrac; ih = rh;
        offset += iw;
      }} else {{
        ix = rx; iy = ry + offset;
        iw = rw; ih = rh * itemFrac;
        offset += ih;
      }}
      layoutTreemap(item, ix + PAD/2, iy + PAD/2, Math.max(0, iw - PAD), Math.max(0, ih - PAD));
    }}

    rTotal -= rowTotal;
  }}
}}

// Rendering
const container = document.getElementById('container');
const tooltip = document.getElementById('tooltip');
const breadcrumbEl = document.getElementById('breadcrumb');
const statsEl = document.getElementById('stats');

let currentRoot = DATA;
let pathStack = [DATA];

function render(root) {{
  sumValues(root);
  const rect = container.getBoundingClientRect();
  layoutTreemap(root, 0, 0, rect.width, rect.height);

  container.innerHTML = '';
  renderNode(root, true);
  updateBreadcrumb();
  updateStats(root);
}}

function renderNode(node, isRoot) {{
  if (!node.children || node.children.length === 0) {{
    // Leaf node (file)
    if (node._w < 3 || node._h < 3) return;

    const el = document.createElement('div');
    el.className = 'node node-leaf';
    el.style.left = node._x + 'px';
    el.style.top = node._y + 'px';
    el.style.width = node._w + 'px';
    el.style.height = node._h + 'px';
    el.style.background = bfBg(node.bus_factor || 0);

    if (node._w > 30 && node._h > 16) {{
      const lbl = document.createElement('div');
      lbl.className = 'node-label';
      lbl.textContent = node.name;
      el.appendChild(lbl);
    }}

    if (node._w > 50 && node._h > 28) {{
      const sc = document.createElement('div');
      sc.className = 'node-score';
      sc.textContent = 'bf:' + (node.bus_factor || '?');
      el.appendChild(sc);
    }}

    el.addEventListener('mouseenter', (e) => showTooltip(e, node));
    el.addEventListener('mousemove', moveTooltip);
    el.addEventListener('mouseleave', hideTooltip);
    container.appendChild(el);
    return;
  }}

  // Directory node
  if (!isRoot) {{
    if (node._w < 8 || node._h < 8) return;

    const el = document.createElement('div');
    el.className = 'node node-dir';
    el.style.left = node._x + 'px';
    el.style.top = node._y + 'px';
    el.style.width = node._w + 'px';
    el.style.height = node._h + 'px';

    if (node._w > 40 && node._h > 20) {{
      const lbl = document.createElement('div');
      lbl.className = 'node-label';
      lbl.textContent = node.name + '/';
      el.appendChild(lbl);
    }}

    el.addEventListener('click', (e) => {{
      e.stopPropagation();
      zoomIn(node);
    }});
    container.appendChild(el);
  }}

  for (const child of node.children) {{
    renderNode(child, false);
  }}
}}

function zoomIn(node) {{
  if (!node.children || node.children.length === 0) return;
  pathStack.push(node);
  currentRoot = node;
  render(node);
}}

function zoomTo(idx) {{
  pathStack = pathStack.slice(0, idx + 1);
  currentRoot = pathStack[pathStack.length - 1];
  render(currentRoot);
}}

function updateBreadcrumb() {{
  breadcrumbEl.innerHTML = '';
  for (let i = 0; i < pathStack.length; i++) {{
    if (i > 0) {{
      const sep = document.createElement('span');
      sep.className = 'sep';
      sep.textContent = ' / ';
      breadcrumbEl.appendChild(sep);
    }}
    const crumb = document.createElement('span');
    crumb.className = 'crumb' + (i === pathStack.length - 1 ? ' active' : '');
    crumb.textContent = i === 0 ? REPO_NAME : pathStack[i].name;
    const idx = i;
    crumb.addEventListener('click', () => zoomTo(idx));
    breadcrumbEl.appendChild(crumb);
  }}
}}

function updateStats(root) {{
  let files = 0, dirs = 0, bf1 = 0, totalBf = 0, bfCount = 0;
  function walk(n) {{
    if (n.value != null) {{
      files++;
      if (n.bus_factor <= 1) bf1++;
      totalBf += n.bus_factor || 0;
      bfCount++;
    }} else if (n.children) {{
      dirs++;
      n.children.forEach(walk);
    }}
  }}
  walk(root);
  const avgBf = bfCount > 0 ? (totalBf / bfCount).toFixed(1) : '?';
  const riskPct = files > 0 ? ((bf1 / files) * 100).toFixed(0) : 0;
  statsEl.innerHTML =
    `<span><span class="stat-val">${{files}}</span> files</span>` +
    `<span><span class="stat-val">${{dirs}}</span> dirs</span>` +
    `<span>avg bf: <span class="stat-val">${{avgBf}}</span></span>` +
    `<span class="${{bf1 > 0 ? 'bf-1' : 'bf-ok'}}"><span class="stat-val">${{riskPct}}%</span> at risk</span>`;
}}

function showTooltip(e, node) {{
  let bfHtml = `<span class="${{bfClass(node.bus_factor || 0)}}">` +
    `Bus Factor: ${{node.bus_factor || '?'}}</span>`;

  let expertsHtml = '';
  if (node.experts && node.experts.length > 0) {{
    expertsHtml = '<div class="tt-experts">';
    for (const ex of node.experts) {{
      expertsHtml += `<div class="tt-expert">` +
        `<span class="name">${{ex.name}}</span>` +
        `<span class="score">${{ex.score}} pts · ${{ex.commits}} commits</span></div>`;
    }}
    expertsHtml += '</div>';
  }}

  tooltip.innerHTML =
    `<div class="tt-path">${{node.path || node.name}}</div>` +
    `<div class="tt-bf">${{bfHtml}}</div>` +
    `<div class="tt-row"><span>Commits</span><span class="tt-val">${{node.commits || 0}}</span></div>` +
    `<div class="tt-row"><span>Lines changed</span><span class="tt-val">${{(node.lines || 0).toLocaleString()}}</span></div>` +
    expertsHtml;
  tooltip.style.display = 'block';
  moveTooltip(e);
}}

function moveTooltip(e) {{
  const pad = 12;
  let x = e.clientX + pad;
  let y = e.clientY + pad;
  const tw = tooltip.offsetWidth;
  const th = tooltip.offsetHeight;
  if (x + tw > window.innerWidth - pad) x = e.clientX - tw - pad;
  if (y + th > window.innerHeight - pad) y = e.clientY - th - pad;
  tooltip.style.left = x + 'px';
  tooltip.style.top = y + 'px';
}}

function hideTooltip() {{ tooltip.style.display = 'none'; }}

// Initial render
render(DATA);
window.addEventListener('resize', () => render(currentRoot));

// Click container background to zoom out
container.addEventListener('click', () => {{
  if (pathStack.length > 1) {{
    pathStack.pop();
    currentRoot = pathStack[pathStack.length - 1];
    render(currentRoot);
  }}
}});
</script>

</body>
</html>"""
