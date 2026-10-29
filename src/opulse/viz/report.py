"""Package registry and expression records into a portable HTML inspection page.

The page uses inline CSS and plain JavaScript so a report can be opened from
disk without a server, package manager, or network connection.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from opulse.analysis.graph import dependency_graph, to_dot
from opulse.core.registry import OperatorRegistry


def _records(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _distribution(values) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def _tree_depth(tree: dict) -> int:
    kind = tree.get("type")
    if kind == "binary":
        return 1 + max(_tree_depth(tree["left_expr"]), _tree_depth(tree["right_expr"]))
    if kind == "unary":
        return 1 + _tree_depth(tree["unary_expr"])
    if kind == "call":
        return 1 + max(_tree_depth(arg) for arg in tree["args"])
    return 1


def _tree_usage(tree: dict, registry: OperatorRegistry) -> Counter:
    """Count every call, including repeated uses of one operator in a tree."""
    kind = tree.get("type")
    if kind == "binary":
        op = registry.find(tree["operator"], 2)
        children = (tree["left_expr"], tree["right_expr"])
    elif kind == "unary":
        op = registry.find(tree["operator"], 1, tree.get("position"))
        children = (tree["unary_expr"],)
    elif kind == "call":
        op = registry.find(tree["operator"], len(tree["args"]))
        children = tuple(tree["args"])
    else:
        return Counter()
    counts = Counter({op.func_id: 1}) if op is not None else Counter()
    for child in children:
        counts.update(_tree_usage(child, registry))
    return counts


def _statistics(graph: dict, expressions: list[dict] | None, registry: OperatorRegistry) -> dict:
    layers: dict[int, list[dict]] = defaultdict(list)
    for node in graph["nodes"]:
        layers[node["recursive_layer"]].append(node)
    operators = []
    for layer, nodes in sorted(layers.items()):
        operators.append({"layer": layer, "count": len(nodes),
                          "definition_type": _distribution(n["definition_type"] or "base" for n in nodes),
                          "arity": _distribution(n["n_ary"] for n in nodes),
                          "position": _distribution(n["unary_position"] or ("binary" if n["n_ary"] == 2 else "call")
                                                    for n in nodes),
                          "max_path_depth": _distribution(n["max_path_depth"] for n in nodes),
                          "max_edge_count": _distribution(n["max_edge_count"] for n in nodes)})
    stats = {"operators": operators}
    if expressions is not None:
        usage = Counter()
        for record in expressions:
            tree = record.get("tree")
            if isinstance(tree, dict):
                usage.update(_tree_usage(tree, registry))
            else:
                usage.update(record.get("used_operators", []))
        stats["expressions"] = {
            "count": len(expressions),
            "nan_count": sum(bool(r.get("undefined") or r.get("result") is None) for r in expressions),
            "results": _distribution(r["result"] for r in expressions
                                     if not r.get("undefined") and r.get("result") is not None),
            "depth": _distribution(_tree_depth(r["tree"]) for r in expressions if isinstance(r.get("tree"), dict)),
            "operator_usage": dict(usage.most_common()),
        }
    return stats


def write_report(operators: Path, out: Path, expressions: Path | None = None) -> Path:
    """Write ``index.html`` and ``graph.dot`` and return the report path."""
    registry = OperatorRegistry.from_jsonl(operators)
    graph = dependency_graph(registry)
    # Operator.from_json intentionally ignores future metadata fields. Preserve
    # those fields in the report so imported properties remain inspectable.
    raw = {row["func_id"]: row for row in _records(operators)}
    for node in graph["nodes"]:
        row = raw[node["func_id"]]
        node.update({key: value for key, value in row.items()
                     if key.startswith(("nl_description", "propert", "complexity")) and value is not None})
    records = _records(expressions) if expressions is not None else None
    from opulse.canary import CANARY, marked

    payload = marked({"graph": graph, "statistics": _statistics(graph, records, registry), "expressions": records})
    # Escaping '<' prevents a definition containing </script> from ending the data tag.
    data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    out.mkdir(parents=True, exist_ok=True)
    (out / "graph.dot").write_text(f"// {CANARY}\n" + to_dot(graph), encoding="utf-8")
    target = out / "index.html"
    target.write_text(_PAGE.replace("__OPULSE_DATA__", data), encoding="utf-8")
    return target


_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Opulse data report</title>
<link rel="icon" href="../images/logo.svg" type="image/svg+xml">
<style>
:root {color-scheme: light dark; --bg:#fff; --text:#17212c; --panel:#f3f6fa; --line:#c5d0dc; --accent:#165e9a; --muted:#53677a}
@media (prefers-color-scheme:dark) {:root {--bg:#141a20; --text:#edf2f7; --panel:#202a34; --line:#536374; --accent:#8ccaff; --muted:#b2c3d2}}
* {box-sizing:border-box} body {margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,sans-serif}
header {padding:1.2rem 2rem;border-bottom:1px solid var(--line)} h1 {margin:0} main {max-width:1500px;margin:auto;padding:1rem 2rem 3rem}
section {margin:1.5rem 0} h2 {margin-bottom:.5rem} .hint {color:var(--muted)}
.grid {display:grid;grid-template-columns:minmax(0,2fr) minmax(260px,1fr);gap:1rem}
.panel {background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:1rem;overflow:auto}
#dag {min-width:100%;height:auto} .node {cursor:pointer} .node rect {fill:var(--bg);stroke:var(--accent);stroke-width:2}
.node:hover rect,.node:focus rect {stroke-width:4} .node text {fill:var(--text);font:13px system-ui,sans-serif;pointer-events:none}
.edge {stroke:var(--line);stroke-width:1.5;fill:none}.loop {stroke:var(--accent)} .layer-label {fill:var(--muted);font:600 14px system-ui,sans-serif}
pre {white-space:pre-wrap;overflow-wrap:anywhere} table {border-collapse:collapse;width:100%} th,td {padding:.4rem .6rem;border-bottom:1px solid var(--line);text-align:left;vertical-align:top} th {white-space:nowrap}
button {font:inherit;color:var(--text);background:var(--panel);border:1px solid var(--line);border-radius:5px;padding:.35rem .7rem;cursor:pointer}
.bars {display:flex;flex-direction:column;gap:.25rem} .bar {display:grid;grid-template-columns:minmax(70px,12rem) 1fr 3rem;gap:.5rem;align-items:center}.bar i {height:.7rem;background:var(--accent);border-radius:2px}
@media(max-width:800px) {.grid {grid-template-columns:1fr} main {padding:1rem} header {padding:1rem}}
</style></head><body><header><h1>Opulse data report</h1><div id="summary" class="hint"></div></header>
<main><section><h2>Dependency DAG</h2><p class="hint">Columns show recursive layers. Arrows point from caller to callee. Select a node for its definition and metadata.</p>
<div class="grid"><div class="panel"><svg id="dag" role="img" aria-label="Operator dependency graph"></svg></div><aside class="panel" id="detail">Select an operator.</aside></div></section>
<section><h2>Per-layer statistics</h2><div class="panel" id="layer-stats"></div></section>
<section id="expression-section"><h2>Expressions</h2><div class="grid"><div class="panel" id="expression-stats"></div><div class="panel"><div><button id="previous">Previous</button> <span id="sample-index"></span> <button id="next">Next</button></div><div id="sample"></div></div></div></section></main>
<script id="report-data" type="application/json">__OPULSE_DATA__</script>
<script>
const data=JSON.parse(document.getElementById('report-data').textContent), graph=data.graph;
const byId=Object.fromEntries(graph.nodes.map(n=>[n.func_id,n]));
const el=(tag,text)=>{const x=document.createElement(tag);if(text!==undefined)x.textContent=String(text);return x};
const add=(parent,tag,text)=>{const x=el(tag,text);parent.append(x);return x};
const list=(object)=>Object.entries(object).map(([k,v])=>`${k}: ${v}`).join(', ')||'—';
document.getElementById('summary').textContent=`${graph.nodes.length} operators · ${graph.edges.length} edges`;
function detail(id){const n=byId[id], root=document.getElementById('detail');root.replaceChildren();
  add(root,'h3',`${n.symbol} · ${id}`);add(root,'p',`${n.n_ary}-ary ${n.unary_position||(n.n_ary==2?'binary':'call')} · layer ${n.recursive_layer} · ${n.definition_type||'base'}`);
  add(root,'h4','Definition');add(root,'pre',n.definition||'Base operator');
  const deps=graph.edges.filter(e=>e.source===id&&e.target!==id).map(e=>byId[e.target].symbol+' ('+e.target+')');
  const users=graph.edges.filter(e=>e.target===id&&e.source!==id).map(e=>byId[e.source].symbol+' ('+e.source+')');
  add(root,'p',`Dependencies: ${deps.join(', ')||'—'}`);add(root,'p',`Dependents: ${users.join(', ')||'—'}`);
  add(root,'p',`In degree: ${n.in_degree} · Out degree: ${n.out_degree} · Transitive dependencies: ${n.transitive_dependencies}`);
  add(root,'p',`Max path depth: ${n.max_path_depth} · Max edge count: ${n.max_edge_count}`);
  for(const [key,value] of Object.entries(n)) if((key.startsWith('nl_description')||key.startsWith('propert')||key.startsWith('complexity'))&&value!=null){
    add(root,'h4',key.replaceAll('_',' '));add(root,'pre',typeof value==='string'?value:JSON.stringify(value,null,2));}
}
const svg=document.getElementById('dag'), ns='http://www.w3.org/2000/svg';
function shape(tag,attrs,parent=svg){const x=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))x.setAttribute(k,v);parent.append(x);return x}
const groups={};for(const n of graph.nodes)(groups[n.recursive_layer]??=[]).push(n);
const layers=Object.keys(groups).map(Number).sort((a,b)=>a-b), positions={};
for(const [column,layer] of layers.entries()){const nodes=groups[layer].sort((a,b)=>a.symbol.localeCompare(b.symbol));
  nodes.forEach((n,row)=>positions[n.func_id]={x:35+column*205,y:55+row*54});}
const maxRows=Math.max(1,...Object.values(groups).map(x=>x.length));
svg.setAttribute('viewBox',`0 0 ${Math.max(300,layers.length*205+50)} ${Math.max(180,maxRows*54+90)}`);
const defs=shape('defs',{}), marker=shape('marker',{id:'arrow',markerWidth:7,markerHeight:7,refX:6,refY:3,orient:'auto'},defs);
shape('path',{d:'M0 0 L6 3 L0 6 Z',fill:'var(--line)'},marker);
for(const edge of graph.edges){const a=positions[edge.source],b=positions[edge.target];
  const d=edge.source===edge.target?`M${a.x+148} ${a.y+12} C${a.x+192} ${a.y-25},${a.x+192} ${a.y+60},${a.x+148} ${a.y+28}`:
    `M${a.x} ${a.y+19} C${(a.x+b.x)/2} ${a.y+19},${(a.x+b.x)/2} ${b.y+19},${b.x+150} ${b.y+19}`;
  shape('path',{d,class:edge.source===edge.target?'edge loop':'edge','marker-end':'url(#arrow)'});}
for(const [column,layer] of layers.entries()){
  const label=shape('text',{x:35+column*205,y:25,class:'layer-label'});label.textContent=`Layer ${layer}`;
  for(const n of groups[layer]){const p=positions[n.func_id],g=shape('g',{class:'node',tabindex:0,role:'button','aria-label':`${n.symbol}, ${n.func_id}`});
    shape('rect',{x:p.x,y:p.y,width:150,height:38,rx:6},g);const t=shape('text',{x:p.x+9,y:p.y+24},g);t.textContent=n.symbol.length>13?n.symbol.slice(0,12)+'…':n.symbol;
    g.addEventListener('click',()=>detail(n.func_id));g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();detail(n.func_id)}});}}
if(graph.nodes.length)detail(graph.nodes[0].func_id);
const table=add(document.getElementById('layer-stats'),'table'), head=add(table,'thead'), tr=add(head,'tr');
for(const h of ['Layer','Count','Definition type','Arity','Position','Max path depth','Max edge count'])add(tr,'th',h);
const body=add(table,'tbody');for(const row of data.statistics.operators){const t=add(body,'tr');
  for(const value of [row.layer,row.count,list(row.definition_type),list(row.arity),list(row.position),list(row.max_path_depth),list(row.max_edge_count)])add(t,'td',value);}
const records=data.expressions;if(records===null)document.getElementById('expression-section').hidden=true;
else{const stats=data.statistics.expressions, root=document.getElementById('expression-stats');
  add(root,'p',`${stats.count} expressions · ${stats.nan_count} NaN results`);
  function bars(title,dist){add(root,'h3',title);const box=add(root,'div');box.className='bars';const entries=Object.entries(dist),peak=Math.max(1,...entries.map(x=>x[1]));
    if(!entries.length)add(box,'p','No data');for(const [label,count] of entries){const line=add(box,'div');line.className='bar';
      add(line,'span',label);const i=add(line,'i');i.style.width=`${100*count/peak}%`;add(line,'span',count);}}
  bars('Result values',stats.results);bars('Expression depth',stats.depth);
  const usage={};for(const [id,count] of Object.entries(stats.operator_usage))usage[`${byId[id]?.symbol||id} (${id})`]=count;
  bars('Operator usage',usage);
  let index=0;function sample(){const box=document.getElementById('sample');box.replaceChildren();
    document.getElementById('sample-index').textContent=records.length?`${index+1} / ${records.length}`:'0 / 0';
    if(!records.length)return;const r=records[index];add(box,'h3',r.expression||'Expression');
    add(box,'p',`Result: ${r.undefined?'NaN':r.result_text??r.result}`);add(box,'h4','Steps');
    if(!r.steps?.length)add(box,'p','No steps');else {const ol=add(box,'ol');for(const step of r.steps)add(ol,'li',step.text||JSON.stringify(step));}}
  document.getElementById('previous').onclick=()=>{index=(index-1+records.length)%records.length;sample()};
  document.getElementById('next').onclick=()=>{index=(index+1)%records.length;sample()};sample();}
</script></body></html>
"""
