/* Growing an operator set: cached real runs, loaded only on selection. */
(function () {
  "use strict";
  const SCRIPT = document.currentScript && document.currentScript.src;
  const DATA_BASE = SCRIPT ? new URL("../data/scales_growth/", SCRIPT) : null;
  const translations = {
    en: {
      scales: "Scale", loading: "Loading operator set…", unavailable: "No completed integer operator set is available at this scale yet.",
      failed: "The operator set could not be loaded.", atoms: "atoms", layer: "layer", simple: "Substitution", branch: "Branch", recursive: "Recursion",
      set: "set", operators: "defined operators", layers: "layers", seed: "seed", time: "generation time", seconds: "s", limit: "The generator has no fixed size limit; one run grew 100,000 operators in about 8.1 hours.",
      full: "Full dependency graph", graphHint: "Wheel or pinch to zoom; drag to pan. Hover or tap for a definition, click to highlight dependencies and dependents.",
      select: "Select an operator to read its definition.", search: "Find symbol", zoomIn: "Zoom in", graphZoomOut: "Zoom out", fit: "Fit", notFound: "Symbol not found.", callsSentence: "calls", more: "and", atomSentence: "This is a base operation.", noCallsSentence: "It has no recorded calls.", calls: "Calls", noCalls: "no recorded calls", atom: "base operation",
      kinds: "Operators by layer and kind", funnel: "Candidate funnel", proposed: "proposed", rejected: "rejected", accepted: "accepted", reasons: "Top rejection reasons", closure: "Dependency closure", chain: "Longest call chain (operators)", span: "Layer span", stats: "per layer: minimum / median / maximum", distribution: "Exact distributions", frequency: "value: count", density: "Dependency density", densityHint: "Rows are callers; columns are callees. Select a layer cell to inspect its finer bins.", zoomOut: "Show layer grid", caller: "caller", callee: "callee", edges: "calls", largest: "Largest closure", deepest: "Deepest chain", definitions: "definitions", chainUnits: "operators", from: "from", to: "to", empty: "No calls in this cell.",
    },
    zh: {
      scales: "规模", loading: "正在加载运算符集…", unavailable: "此规模尚无已完成的整数运算符集。",
      failed: "无法加载运算符集。", atoms: "原子操作", layer: "层", simple: "代入", branch: "分支", recursive: "递归",
      set: "运算符集", operators: "已定义运算符", layers: "层数", seed: "种子", time: "生成时间", seconds: "秒", limit: "生成器没有固定的数量上限；一次运行在约 8.1 小时内生成了 100,000 个运算符。",
      full: "完整依赖图", graphHint: "滚轮或双指缩放，拖动平移。悬停或轻触查看定义，点击高亮依赖和调用者。",
      select: "选择运算符以查看定义。", search: "查找符号", zoomIn: "放大", graphZoomOut: "缩小", fit: "适配", notFound: "未找到符号。", callsSentence: "调用", more: "另有", atomSentence: "这是基础操作。", noCallsSentence: "没有记录的调用。", calls: "调用", noCalls: "无记录的调用", atom: "基础操作",
      kinds: "各层运算符及类型", funnel: "候选项统计", proposed: "提出", rejected: "拒绝", accepted: "接受", reasons: "主要拒绝原因", closure: "依赖闭包", chain: "最长调用链（运算符数）", span: "跨越层数", stats: "各层：最小值 / 中位数 / 最大值", distribution: "完整分布", frequency: "取值：数量", density: "依赖密度", densityHint: "行是调用者，列是被调用者。点击层格子可查看更细的区间。", zoomOut: "显示层网格", caller: "调用者", callee: "被调用者", edges: "调用", largest: "最大闭包", deepest: "最深调用链", definitions: "定义", chainUnits: "个运算符", from: "从", to: "到", empty: "此格没有调用。",
    }
  };
  const choices = [["int10"], ["int100"], ["int1000"], ["int10000b"]];
  const sizes = ["≈10", "≈100", "≈1000", "≈10000"];
  const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  const fmt = n => Number(n).toLocaleString();
  const sum = a => a.reduce((v, n) => v + n, 0);
  const node = (tag, cls, parent, content) => { const e = document.createElement(tag); e.className = cls; if (content !== undefined) e.innerHTML = content; parent.appendChild(e); return e; };
  const REASON_LABELS = {
    en: {
      "wrong layer": "wrong layer", "unused parameter": "unused parameter",
      "single call of the same arity": "just repeats a call", "duplicate branch bodies": "identical branches",
      "duplicate body": "same definition", "compiled code disagrees with reference": "disagrees with reference",
      "disagrees with reference": "disagrees with reference", "undefined on all samples": "undefined for every sample",
      "nearly constant": "nearly constant", "mostly returns an input": "mostly returns an input",
      "defined on too few inputs": "undefined too often", "degenerate subexpression": "constant subexpression",
      "dead branch": "dead branch", "undefined branch": "undefined branch",
      "behavioural duplicate": "same as an existing operator",
      "behavioural duplicate up to argument order": "same after swapping inputs",
      "behavioural duplicate up to negation": "same after negation",
      "behavioural duplicate up to argument order and negation": "same after swapping and negating",
      "draft": "could not make a candidate",
    },
    zh: {
      "wrong layer": "层数不符", "unused parameter": "未使用参数",
      "single call of the same arity": "只重复一次调用", "duplicate branch bodies": "分支内容相同",
      "duplicate body": "定义相同", "compiled code disagrees with reference": "与参考结果不符",
      "disagrees with reference": "与参考结果不符", "undefined on all samples": "所有样本都无定义",
      "nearly constant": "结果几乎不变", "mostly returns an input": "结果大多等于输入",
      "defined on too few inputs": "未定义的输入过多", "degenerate subexpression": "子式结果恒定",
      "dead branch": "不可达分支", "undefined branch": "无定义分支",
      "behavioural duplicate": "与已有运算符行为相同",
      "behavioural duplicate up to argument order": "交换参数后与已有运算符相同",
      "behavioural duplicate up to negation": "取反后与已有运算符相同",
      "behavioural duplicate up to argument order and negation": "交换参数并取反后与已有运算符相同",
      "draft": "无法生成候选项",
    },
  };
  const reasonKey = (reason) => {
    if (reason.startsWith("unused parameter ")) return "unused parameter";
    if (reason.startsWith("disagrees with reference:")) return "disagrees with reference";
    if (/^(dead|undefined) branch \d+$/.test(reason)) return reason.split(" ").slice(0, 2).join(" ");
    if (reason.startsWith("draft: ")) return "draft";
    return reason;
  };
  const reasonLabel = (reason, t) => REASON_LABELS[t === translations.zh ? "zh" : "en"][reasonKey(reason)] || reason;
  const hist = (pairs, t) => {
    const total = sum(pairs.map(x => x[1])); let at = 0, middle = pairs[0][0];
    for (const [value, count] of pairs) { at += count; if (at * 2 >= total) { middle = value; break; } }
    return `${fmt(pairs[0][0])} / ${fmt(middle)} / ${fmt(pairs[pairs.length - 1][0])}`;
  };
  function graphView(parent, data, t) {
    node("h3", "", parent, t.full);
    node("p", "sg-note", parent, esc(t.graphHint));
    if (!window.OpGraph) { node("p", "sg-note", parent, esc(t.failed)); return null; }
    return window.OpGraph.mount(parent, data.graph, data._definitions, {
      graph:t.full, search:t.search, zoomIn:t.zoomIn, zoomOut:t.graphZoomOut, fit:t.fit,
      select:t.select, notFound:t.notFound, kinds:[t.atom,t.simple,t.branch,t.recursive],
      atoms:t.atoms, layer:t.layer, atom:t.atom, callsSentence:t.callsSentence,
      noCalls:t.noCalls, more:t.more, atomSentence:t.atomSentence,
      noCallsSentence:t.noCallsSentence,
    });
  }
  function bars(parent, data, t) {
    node("h3","",parent,t.kinds);
    const max = Math.max(...data.layers.map(x=>x.count));
    const list = node("div","sg-kind-list",parent);
    for (const row of data.layers) {
      const line = node("div","sg-kind-row",list);
      node("span","",line,`${esc(t.layer)} ${row.layer}`);
      const track=node("div","sg-kind-track",line);
      for (const kind of ["simple","branch","recursive"]) {
        const count=row.kinds[kind];
        const segment=node("span",`sg-${kind}`,track);
        segment.style.width=`${100*count/max}%`;
        segment.title=`${t[kind]}: ${count}`;
      }
      node("b","",line,fmt(row.count));
    }
    node("p","sg-legend",parent,["simple","branch","recursive"].map(k=>`<span class="sg-${k}">● ${esc(t[k])}</span>`).join(" "));
    const kindLegend = node("div", "", parent);
    if (window.KindsLegend) window.KindsLegend.render(kindLegend);
  }
  function funnel(parent,data,t) {
    node("h3","",parent,t.funnel);
    node("p","sg-summary",parent,`${esc(t.proposed)} <b>${fmt(data.proposed)}</b> → ${esc(t.rejected)} <b>${fmt(data.proposed-data.size)}</b> + ${esc(t.accepted)} <b>${fmt(data.size)}</b>`);
    const grouped=new Map();
    for(const [reason,count] of Object.entries(data.rejected)){
      const key=reasonKey(reason), group=grouped.get(key)||{count:0,raw:[]};
      group.count+=count; group.raw.push(reason); grouped.set(key,group);
    }
    const top=[...grouped].sort((a,b)=>b[1].count-a[1].count).slice(0,5);
    node("p","sg-note",parent,`${esc(t.reasons)}: ${top.map(([reason,group])=>`<span title="${esc(group.raw.join("; "))}">${esc(reasonLabel(reason,t))} ${fmt(group.count)}</span>`).join(" · ")}`);
    const table=node("div","sg-scroll",parent);
    table.innerHTML=`<table><thead><tr><th>${esc(t.layer)}</th><th>${esc(t.proposed)}</th><th>${esc(t.rejected)}</th><th>${esc(t.accepted)}</th></tr></thead><tbody>${data.funnel.map(r=>`<tr><th>${r.layer}</th><td>${fmt(r.accepted+r.rejected)}</td><td>${fmt(r.rejected)}</td><td>${fmt(r.accepted)}</td></tr>`).join("")}</tbody></table>`;
  }
  function depth(parent,data,t) {
    node("h3","",parent,`${esc(t.closure)} · ${esc(t.chain)}`);
    node("p","sg-note",parent,esc(t.stats));
    const table=node("div","sg-scroll",parent);
    table.innerHTML=`<table><thead><tr><th>${esc(t.layer)}</th><th>${esc(t.closure)}</th><th>${esc(t.chain)}</th><th>${esc(t.span)}</th></tr></thead><tbody>${data.layers.map(r=>`<tr><th>${r.layer}</th><td>${hist(r.closure,t)}</td><td>${hist(r.chain,t)}</td><td>${hist(r.layer_span,t)}</td></tr>`).join("")}</tbody></table>`;
    const a=data.largest_closure,b=data.deepest_chain;
    node("p","sg-note",parent,`${esc(t.largest)}: <b>${esc(a.symbol)}</b> (${esc(t.layer)} ${a.layer}, ${fmt(a.closure)}). ${esc(t.deepest)}: <b>${esc(b.symbol)}</b> (${esc(t.layer)} ${b.layer}, ${fmt(b.chain)} ${esc(t.chainUnits)}).`);
    const exact=node("details","",parent);
    exact.innerHTML=`<summary>${esc(t.distribution)}</summary>${data.layers.map(r=>`<p>${esc(t.layer)} ${r.layer}: ${esc(t.closure)} ${r.closure.map(x=>`${x[0]}:${x[1]}`).join(" · ")}<br>${esc(t.chain)} ${r.chain.map(x=>`${x[0]}:${x[1]}`).join(" · ")}<br>${esc(t.span)} ${r.layer_span.map(x=>`${x[0]}:${x[1]}`).join(" · ")}</p>`).join("")}`;
  }
  function heatmap(parent,data,t) {
    node("h3","",parent,t.density);
    node("p","sg-note",parent,esc(t.densityHint));
    const container=node("div","sg-heat",parent);
    const caption=node("p","sg-note",parent,"");
    const labels=data.density.layers,matrix=data.density.layer_matrix;
    const max=Math.max(1,...matrix.flat());
    const showGrid=() => {
      container.replaceChildren();
      caption.textContent="";
      const grid=node("div","sg-layer-grid",container);
      grid.style.gridTemplateColumns=`minmax(3.1rem,auto) repeat(${labels.length},minmax(1.4rem,1fr))`;
      node("span","",grid,"");
      labels.forEach(l=>node("span","sg-grid-label",grid,l<0?esc(t.atoms):`${esc(t.layer)} ${l}`));
      matrix.forEach((row,i)=>{
        node("span","sg-grid-label",grid,labels[i]<0?esc(t.atoms):`${esc(t.layer)} ${labels[i]}`);
        row.forEach((value,j)=>{
          const button=node("button","sg-cell",grid,value?fmt(value):"·");
          button.type="button";
          button.style.setProperty("--intensity",`${(85*Math.sqrt(value/max)).toFixed(1)}%`);
          button.title=`${t.caller} ${labels[i]} → ${t.callee} ${labels[j]}: ${value} ${t.edges}`;
          button.setAttribute("aria-label",button.title);
          button.addEventListener("click",()=>showFine(i,j));
        });
      });
    };
    const showFine=(i,j)=>{
      container.replaceChildren();
      const back=node("button","sg-back",container,esc(t.zoomOut));
      back.type="button"; back.addEventListener("click",showGrid);
      const bins=data.density.bins,n=data.size+data.density.layer_ranges[0][1];
      const [a0,a1]=data.density.layer_ranges[i], [b0,b1]=data.density.layer_ranges[j];
      const ai0=Math.floor(a0*bins/n),ai1=Math.min(bins,Math.ceil(a1*bins/n));
      const bj0=Math.floor(b0*bins/n),bj1=Math.min(bins,Math.ceil(b1*bins/n));
      const fine=data.density.fine;
      const canvas=node("canvas","sg-canvas",container);
      canvas.width=Math.max(1,ai1-ai0); canvas.height=Math.max(1,bj1-bj0);
      const ctx=canvas.getContext("2d");
      const local=[];
      for(let a=ai0;a<ai1;a++) for(let b=bj0;b<bj1;b++) local.push(fine[a][b]);
      const top=Math.max(1,...local);
      local.forEach((v,index)=>{const row=Math.floor(index/(bj1-bj0)),col=index%(bj1-bj0);ctx.fillStyle=`rgba(42,148,190,${v?0.12+0.88*Math.sqrt(v/top):0.03})`;ctx.fillRect(row,col,1,1);});
      caption.textContent=`${t.caller} ${labels[i]} → ${t.callee} ${labels[j]}: ${fmt(matrix[i][j])} ${t.edges}. ${matrix[i][j] ? `${t.from} ${ai0} ${t.to} ${ai1-1}; ${t.from} ${bj0} ${t.to} ${bj1-1}.` : t.empty}`;
    };
    showGrid();
  }
  function show(parent,data,t) {
    parent.replaceChildren();
    node("p","sg-meta",parent,`${esc(t.set)} <b>${esc(data.set)}</b> · <b>${fmt(data.size)}</b> ${esc(t.operators)} · <b>${data.layers.length}</b> ${esc(t.layers)} · ${esc(t.seed)} <b>${data.seed}</b> · ${esc(t.time)} <b>${fmt(data.seconds)} ${esc(t.seconds)}</b>`);
    node("p","sg-note",parent,esc(t.limit));
    const graph = data.graph ? graphView(parent,data,t) : null;
    bars(parent,data,t); funnel(parent,data,t); depth(parent,data,t); heatmap(parent,data,t);
    return graph;
  }
  function init() {
    document.querySelectorAll(".scales-growth:not([data-ready])").forEach(root=>{
      root.dataset.ready="1";
      const t=translations[root.dataset.lang || (location.pathname.includes("/zh/") ? "zh" : "en")];
      const base=DATA_BASE;
      const cache={};
      const tabs=node("div","sg-tabs",root);
      tabs.setAttribute("role","tablist");tabs.setAttribute("aria-label",t.scales);
      const panel=node("div","sg-panel",root);
      panel.id=`sg-panel-${Math.random().toString(36).slice(2)}`;
      panel.setAttribute("role","tabpanel");panel.setAttribute("tabindex","0");
      const buttons=choices.map((_,i)=>{
        const b=node("button","sg-tab",tabs,sizes[i]); b.type="button";
        b.setAttribute("role","tab");b.setAttribute("aria-controls",panel.id);
        b.setAttribute("aria-label",`${sizes[i]} ${t.operators}`);
        b.addEventListener("click",()=>select(i));
        b.addEventListener("keydown",e=>{
          const d=e.key==="ArrowRight"?1:e.key==="ArrowLeft"?-1:0;
          if(d){e.preventDefault();const next=(i+d+choices.length)%choices.length;buttons[next].focus();select(next);}
          if(e.key==="Home"||e.key==="End"){e.preventDefault();const next=e.key==="Home"?0:choices.length-1;buttons[next].focus();select(next);}
        });
        return b;
      });
      let current=-1, mounted=null;
      async function select(i){
        if(mounted){mounted.destroy();mounted=null;}
        current=i; buttons.forEach((b,k)=>{b.setAttribute("aria-selected",String(k===i));b.tabIndex=k===i?0:-1;});
        panel.replaceChildren();
        node("p","sg-note",panel,esc(t.loading));
        try{
          let data=null;
          for(const id of choices[i]){
            if(cache[id]){data=cache[id];break;}
            const response=await fetch(new URL(`${id}.json`,base));
            if(response.status===404)continue;
            if(!response.ok)throw Error(response.status);
            data=await response.json();
            if (data.graph) {
              const details=await fetch(new URL(data.graph.definitions,base));
              if (!details.ok) throw Error(details.status);
              data._definitions=await details.json();
            }
            cache[id]=data;break;
          }
          if(current===i){
            if(data)mounted=show(panel,data,t);
            else{panel.replaceChildren();node("p","sg-note",panel,esc(t.unavailable));}
          }
        }catch(error){if(current===i){panel.replaceChildren();node("p","sg-note",panel,esc(t.failed));}}
      }
      select(0);
    });
  }
  if(window.document$) window.document$.subscribe(init);
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",init); else init();
})();
