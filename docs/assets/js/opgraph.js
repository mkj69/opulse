/* Shared, pre-laid-out operator dependency graph. Graph schema: nodes [symbol, layer, kind, rank], flat index edges. */
(function (root) {
  "use strict";
  const X_STEP = 176, Y_STEP = 38, BOX_W = 116, BOX_H = 27, TOP = 46;
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const worldToScreen = (x, y, view) => ({x: x * view.scale + view.x, y: y * view.scale + view.y});
  const screenToWorld = (x, y, view) => ({x: (x - view.x) / view.scale, y: (y - view.y) / view.scale});
  const zoomAt = (view, scale, x, y) => {
    const point = screenToWorld(x, y, view);
    return {scale, x: x - point.x * scale, y: y - point.y * scale};
  };
  const hitTest = (nodes, view, sx, sy) => {
    const p = screenToWorld(sx, sy, view);
    const layer = Math.round((p.x - BOX_W / 2 - 18) / X_STEP) - 1;
    const rank = Math.round((p.y - TOP - BOX_H / 2) / Y_STEP);
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      if (n[1] === layer && n[3] === rank &&
          Math.abs(p.x - (18 + (layer + 1) * X_STEP + BOX_W / 2)) <= BOX_W / 2 + 5 &&
          Math.abs(p.y - (TOP + rank * Y_STEP + BOX_H / 2)) <= BOX_H / 2 + 5) return i;
    }
    return -1;
  };
  const geometry = {worldToScreen, screenToWorld, zoomAt, hitTest};
  if (typeof module !== "undefined" && module.exports) module.exports = geometry;
  if (!root || !root.document) return;

  function mount(host, graph, definitions, labels) {
    const nodes = graph.nodes, pairs = graph.edges;
    const doc = root.document;
    const make = (tag, cls, parent) => {
      const el = doc.createElement(tag); el.className = cls; parent.appendChild(el); return el;
    };
    const wrap = make("section", "og", host);
    const bar = make("div", "og-tools", wrap);
    const search = make("input", "og-search", bar);
    search.type = "search"; search.placeholder = labels.search; search.setAttribute("aria-label", labels.search);
    const button = (caption, title, fn) => { const b = make("button", "og-button", bar); b.type = "button"; b.textContent = caption; b.title = title; b.setAttribute("aria-label", title); b.addEventListener("click", fn); return b; };
    const viewport = make("div", "og-viewport", wrap);
    viewport.setAttribute("aria-label", labels.graph);
    viewport.tabIndex = 0;
    const useCanvas = nodes.length > 300;
    const surface = useCanvas ? make("canvas", "og-surface", viewport) : doc.createElementNS("http://www.w3.org/2000/svg", "svg");
    if (!useCanvas) { surface.setAttribute("class", "og-surface"); viewport.appendChild(surface); }
    const detail = make("div", "og-detail", wrap);
    detail.setAttribute("aria-live", "polite"); detail.textContent = labels.select;
    const byLayer = new Map(), outgoing = Array.from({length:nodes.length},()=>[]), incoming = Array.from({length:nodes.length},()=>[]);
    let maxRank = 0, maxLayer = -1;
    nodes.forEach((n,i) => { if (!byLayer.has(n[1])) byLayer.set(n[1], []); byLayer.get(n[1]).push(i); maxRank=Math.max(maxRank,n[3]); maxLayer=Math.max(maxLayer,n[1]); });
    for (const group of byLayer.values()) group.sort((a,b)=>nodes[a][3]-nodes[b][3]);
    const bundles=new Map();
    for (let e=0; e<pairs.length; e+=2) {
      const a=pairs[e], b=pairs[e+1];outgoing[a].push(b);incoming[b].push(a);
      if(nodes[a][1]!==nodes[b][1]){
        const key=`${nodes[a][1]},${nodes[b][1]}`;bundles.set(key,(bundles.get(key)||0)+1);
      }
    }
    const worldW = (maxLayer + 1) * X_STEP + BOX_W + 36, worldH = TOP + (maxRank+1)*Y_STEP + 32;
    const pos = i => ({x:18+(nodes[i][1]+1)*X_STEP, y:TOP+nodes[i][3]*Y_STEP});
    let view = {scale:1,x:0,y:0}, width=1, height=1, selected=-1, hovered=-1, closure=null, dependents=null, pending=false;
    let pointer = null, pinch = null;
    const colors = () => {
      const style = getComputedStyle(wrap);
      return ["--og-atom","--og-simple","--og-branch","--og-recursive"].map(k=>style.getPropertyValue(k).trim());
    };
    function fit() { const scale = clamp(Math.min((width-32)/worldW,(height-32)/worldH), .004, 2); view={scale,x:(width-worldW*scale)/2,y:(height-worldH*scale)/2}; queue(); }
    function show(i) {
      if (i < 0) { detail.textContent=labels.select; return; }
      const n=nodes[i], calls=outgoing[i].filter(j=>j!==i).map(j=>nodes[j][0]);
      detail.replaceChildren();
      const strong=make("strong","",detail); strong.textContent=n[0];
      detail.append(` · ${labels.kinds[n[2]]} · ${n[1]<0?labels.atoms:labels.layer+" "+n[1]}`);
      const code=make("code","",detail); code.textContent=definitions[i] || labels.atom;
      const sentence=make("p","",detail);
      sentence.textContent=n[2]===0 ? labels.atomSentence :
        calls.length ? `${n[0]} ${labels.callsSentence} ${calls.slice(0,8).join(", ")}${calls.length>8?` ${labels.more} ${calls.length-8}`:""}.` : labels.noCallsSentence;
    }
    function reach(start, links) {
      const seen=new Uint8Array(nodes.length), stack=[start]; seen[start]=1;
      while(stack.length) for(const j of links[stack.pop()]) if(!seen[j]){seen[j]=1;stack.push(j);}
      return seen;
    }
    function choose(i) { selected=i; closure=i<0?null:reach(i,outgoing); dependents=i<0?null:reach(i,incoming); show(i); queue(); }
    function openOverview(sx,sy) {
      const layers=[...byLayer.keys()].sort((a,b)=>a-b);
      const column=clamp(Math.round(sx*(layers.length+1)/width)-1,0,layers.length-1);
      const group=byLayer.get(layers[column]);
      const rank=clamp(Math.floor((sy-42)/(height-47)*group.length),0,group.length-1);
      const p=pos(group[rank]);
      view={scale:.8,x:sx-(p.x+BOX_W/2)*.8,y:sy-(p.y+BOX_H/2)*.8};queue();
    }
    function zoom(factor) { if(view.scale<.12&&factor>1){openOverview(width/2,height/2);return;} view=zoomAt(view,clamp(view.scale*factor,.004,5),width/2,height/2); queue(); }
    button("−",labels.zoomOut,()=>zoom(1/1.6)); button("+",labels.zoomIn,()=>zoom(1.6)); button(labels.fit,labels.fit,fit);
    search.addEventListener("change",()=>{ const query=search.value.trim().toLocaleLowerCase(); if(!query)return; const i=nodes.findIndex(n=>n[0].toLocaleLowerCase()===query); const j=i>=0?i:nodes.findIndex(n=>n[0].toLocaleLowerCase().includes(query)); if(j<0){detail.textContent=labels.notFound;return;} const p=pos(j); view={scale:Math.max(view.scale,1.3),x:width/2-(p.x+BOX_W/2)*Math.max(view.scale,1.3),y:height/2-(p.y+BOX_H/2)*Math.max(view.scale,1.3)}; choose(j); });
    const active = i => !closure || closure[i] || dependents[i];
    function visible() { const a=screenToWorld(-BOX_W,-BOX_H,view), b=screenToWorld(width+BOX_W,height+BOX_H,view); return {left:a.x,right:b.x,top:a.y,bottom:b.y}; }
    function drawCanvas() {
      const dpr=Math.min(root.devicePixelRatio||1,2), cw=Math.max(1,Math.round(width*dpr)), ch=Math.max(1,Math.round(height*dpr));
      if(surface.width!==cw||surface.height!==ch){surface.width=cw;surface.height=ch;}
      const ctx=surface.getContext("2d"); if(!ctx)return;
      ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,width,height);
      ctx.globalAlpha=1;ctx.textAlign="left";
      const c=colors(), v=visible(), detailed=view.scale>=.72, dots=view.scale>=.12, fg=getComputedStyle(wrap).color;
      // In the overview, compress each ordered layer into a column of density dots.
      // Its layout is screen-based so even a 10,000-node set keeps all layers visible.
      if(view.scale<.12){
        const columns=[...byLayer].sort((a,b)=>a[0]-b[0]);
        const gap=width/(columns.length+1), bins=Math.max(24,Math.min(120,Math.floor((height-55)/4)));
        const layerColumn=new Map(columns.map(([layer],i)=>[layer,i]));
        ctx.lineWidth=1;
        for(const [key,count] of bundles){const [from,to]=key.split(",").map(Number),a=layerColumn.get(from),b=layerColumn.get(to);
          if(a===undefined||b===undefined)continue;
          const x1=gap*(a+1),x2=gap*(b+1),y1=height*.4+a*3,y2=height*.4+b*3;
          ctx.strokeStyle=fg;ctx.globalAlpha=Math.min(.16,.025+.012*Math.log1p(count));
          ctx.beginPath();ctx.moveTo(x1,y1);ctx.bezierCurveTo((x1+x2)/2,y1,(x1+x2)/2,y2,x2,y2);ctx.stroke();
        }
        ctx.globalAlpha=1;ctx.font="11px sans-serif";ctx.textAlign="center";
        columns.forEach(([layer,group],column)=>{
          const x=gap*(column+1), hist=Array.from({length:bins},()=>[0,0,0,0]);
          for(const i of group) hist[Math.min(bins-1,Math.floor(nodes[i][3]*bins/Math.max(1,group.length)))][nodes[i][2]]++;
          ctx.fillStyle=fg;ctx.fillText(layer<0?labels.atoms:`${labels.layer} ${layer}`,x,18,Math.max(20,gap-3));
          ctx.fillText(String(group.length),x,35);
          const dot=Math.max(2,Math.min(5,gap/7)), yStep=(height-47)/bins;
          for(let k=0;k<bins;k++){
            const total=hist[k].reduce((a,b)=>a+b,0);if(!total)continue;
            let left=x-2*dot;
            for(let kind=0;kind<4;kind++)if(hist[k][kind]){
              ctx.globalAlpha=.2+.75*Math.sqrt(hist[k][kind]/total);
              ctx.fillStyle=c[k];ctx.fillRect(left,42+k*yStep,dot,Math.max(2,yStep-1));left+=dot;
            }
          }
          ctx.globalAlpha=1;
        });
        return;
      }
      ctx.font="12px sans-serif";
      for(const [layer, group] of byLayer){const x=worldToScreen(18+(layer+1)*X_STEP,0,view).x;if(x < -BOX_W || x > width+BOX_W)continue;
        ctx.fillStyle=c[layer<0?0:1]; ctx.globalAlpha=.13; ctx.fillRect(x,24,Math.max(5,BOX_W*view.scale),height-24); ctx.globalAlpha=1;
        ctx.fillStyle=fg; ctx.fillText(layer<0?labels.atoms:`${labels.layer} ${layer}`,x,16);
        if(!dots){
          const bins=64, counts=new Uint16Array(bins);
          for(const i of group) counts[Math.min(bins-1,Math.floor(nodes[i][3]*bins/(maxRank+1)))]++;
          const top=Math.max(1,...counts);
          for(let k=0;k<bins;k++) if(counts[k]){
            ctx.globalAlpha=.2+.75*Math.sqrt(counts[k]/top); ctx.fillStyle=c[layer<0?0:1];
            ctx.fillRect(x,25+k*(height-32)/bins,Math.max(3,BOX_W*view.scale),Math.max(2,(height-32)/bins-1));
          }
          ctx.globalAlpha=1; ctx.fillStyle=fg;ctx.fillText(String(group.length),x,34);
        }
      }
      // Edges appear only when their endpoints can be read. This keeps large views responsive.
      if(detailed) {
        ctx.lineWidth=1.15;
        for(const [layer, group] of byLayer){const x=18+(layer+1)*X_STEP;if(x<v.left-BOX_W||x>v.right+BOX_W)continue;
          for(const i of group){const p=pos(i);if(p.y<v.top-BOX_H||p.y>v.bottom+BOX_H)continue;
            for(const j of outgoing[i]){const q=pos(j);if(q.x<v.left-BOX_W||q.x>v.right+BOX_W||q.y<v.top-BOX_H||q.y>v.bottom+BOX_H)continue;
              const same=nodes[i][1]===nodes[j][1];
              const a=worldToScreen(p.x+(same?BOX_W:0),p.y+BOX_H/2,view), b=worldToScreen(q.x+BOX_W,q.y+BOX_H/2,view);
              ctx.strokeStyle=selected>=0 && closure[i] && closure[j]?c[2]:fg;
              ctx.globalAlpha=selected>=0 && !active(i)? .06 : selected>=0?.6:.18;
              ctx.beginPath();
              if(i===j){ctx.moveTo(a.x-BOX_W*view.scale*.35,a.y-BOX_H*view.scale/2);ctx.bezierCurveTo(a.x-20,a.y-34,a.x+20,a.y-34,a.x-BOX_W*view.scale*.6,a.y-BOX_H*view.scale/2);}
              else if(same){ctx.moveTo(a.x,a.y);ctx.bezierCurveTo(a.x+32,a.y,b.x+32,b.y,b.x,b.y);}
              else{ctx.moveTo(a.x,a.y);const mid=(a.x+b.x)/2;ctx.bezierCurveTo(mid,a.y,mid,b.y,b.x,b.y);}
              ctx.stroke();
              {const end=i===j?{x:a.x-BOX_W*view.scale*.6,y:a.y-BOX_H*view.scale/2}:b;
                const angle=i===j?Math.atan2(34,-20-BOX_W*view.scale*.6):same?Math.atan2(b.y-a.y,-32):Math.atan2(b.y-a.y,b.x-a.x);
                ctx.beginPath();ctx.moveTo(end.x,end.y);ctx.lineTo(end.x-7*Math.cos(angle-.45),end.y-7*Math.sin(angle-.45));ctx.lineTo(end.x-7*Math.cos(angle+.45),end.y-7*Math.sin(angle+.45));ctx.closePath();ctx.fillStyle=ctx.strokeStyle;ctx.fill();}
            }
          }
        }
        ctx.globalAlpha=1;
      }
      if(!dots)return;
      for(const [layer,group] of byLayer){const x=18+(layer+1)*X_STEP;if(x<v.left-BOX_W||x>v.right+BOX_W)continue;
        for(const i of group){const p=pos(i);if(p.y<v.top-BOX_H||p.y>v.bottom+BOX_H)continue;const s=worldToScreen(p.x,p.y,view), n=nodes[i], color=c[n[2]];
          ctx.globalAlpha=selected>=0&&!active(i)?.13:1;ctx.fillStyle=color;
          if(!detailed){ctx.beginPath();ctx.arc(s.x+3,s.y+3,Math.max(1.3,Math.min(3,view.scale*5)),0,Math.PI*2);ctx.fill();continue;}
          const w=BOX_W*view.scale,h=BOX_H*view.scale,r=Math.min(8*view.scale,h/2);
          ctx.globalAlpha=selected>=0&&!active(i)?.16:.14;ctx.beginPath();if(ctx.roundRect)ctx.roundRect(s.x,s.y,w,h,r);else ctx.rect(s.x,s.y,w,h);ctx.fill();ctx.globalAlpha=selected>=0&&!active(i)?.2:1;ctx.strokeStyle=color;ctx.lineWidth=i===selected?2.5:1.2;ctx.stroke();
          ctx.fillStyle=fg;ctx.font=`${Math.max(10,12*view.scale)}px monospace`;ctx.textAlign="center";ctx.fillText(n[0],s.x+w/2,s.y+h/2+4*view.scale,w-8);
        }
      }ctx.globalAlpha=1;
    }
    function drawSVG() {
      surface.replaceChildren(); surface.setAttribute("viewBox",`0 0 ${width} ${height}`); surface.setAttribute("width",width);surface.setAttribute("height",height);
      const ns="http://www.w3.org/2000/svg", c=colors(), v=visible();
      const el=(tag,attrs,parent=surface)=>{const e=doc.createElementNS(ns,tag);for(const [k,val] of Object.entries(attrs))e.setAttribute(k,val);parent.appendChild(e);return e;};
      for(const [layer] of byLayer){const x=worldToScreen(18+(layer+1)*X_STEP,0,view).x;if(x < -BOX_W||x>width+BOX_W)continue; const t=el("text",{x,y:18,fill:"currentColor","font-size":12});t.textContent=layer<0?labels.atoms:`${labels.layer} ${layer}`;}
      for(let e=0;e<pairs.length;e+=2){const i=pairs[e],j=pairs[e+1],p=pos(i),q=pos(j);if(p.x<v.left-BOX_W||p.x>v.right+BOX_W||p.y<v.top-BOX_H||p.y>v.bottom+BOX_H)continue;
        const same=nodes[i][1]===nodes[j][1],a=worldToScreen(p.x+(same?BOX_W:0),p.y+BOX_H/2,view),b=worldToScreen(q.x+BOX_W,q.y+BOX_H/2,view),mid=(a.x+b.x)/2;
        const path=i===j?`M${a.x-BOX_W*view.scale*.35} ${a.y-BOX_H*view.scale/2} C${a.x-20} ${a.y-34} ${a.x+20} ${a.y-34} ${a.x-BOX_W*view.scale*.6} ${a.y-BOX_H*view.scale/2}`:
          same?`M${a.x} ${a.y} C${a.x+32} ${a.y} ${b.x+32} ${b.y} ${b.x} ${b.y}`:
          `M${a.x} ${a.y} C${mid} ${a.y} ${mid} ${b.y} ${b.x} ${b.y}`;
        el("path",{d:path,fill:"none",stroke: selected>=0&&closure[i]&&closure[j]?c[2]:"currentColor","stroke-opacity":selected>=0&&!active(i)?.08:.28,"stroke-width":selected>=0?2:1.1});
        if(i===j){const tipX=a.x-BOX_W*view.scale*.6,tipY=a.y-BOX_H*view.scale/2;
          el("path",{d:`M${tipX} ${tipY} l6 -4 l-1 7 z`,fill:c[nodes[i][2]],opacity:.65});
        }else el("path",{d:`M${b.x} ${b.y} l7 -3 v6 z`,fill:c[nodes[i][2]],opacity:.5});
      }
      nodes.forEach((n,i)=>{const p=pos(i);if(p.x<v.left-BOX_W||p.x>v.right+BOX_W||p.y<v.top-BOX_H||p.y>v.bottom+BOX_H)return;const s=worldToScreen(p.x,p.y,view),g=el("g",{opacity:selected>=0&&!active(i)?.16:1,role:"button",tabindex:"0","aria-label":n[0]});
        el("rect",{x:s.x,y:s.y,width:BOX_W*view.scale,height:BOX_H*view.scale,rx:8*view.scale,fill:c[n[2]],"fill-opacity":.13,stroke:c[n[2]],"stroke-width":i===selected?2.5:1.2},g);
        const t=el("text",{x:s.x+BOX_W*view.scale/2,y:s.y+BOX_H*view.scale/2+4,"text-anchor":"middle",fill:"currentColor","font-size":12*view.scale,"font-family":"monospace"},g);t.textContent=n[0];
        g.addEventListener("mouseenter",()=>{hovered=i;show(i);});g.addEventListener("click",()=>choose(i));g.addEventListener("focus",()=>show(i));g.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();choose(i);}});
      });
    }
    function draw(){pending=false;if(!viewport.isConnected)return;useCanvas?drawCanvas():drawSVG();}
    function queue(){if(!pending){pending=true;root.requestAnimationFrame(draw);}}
    function resize(){const rect=viewport.getBoundingClientRect();width=Math.max(1,rect.width);height=Math.max(1,rect.height);queue();}
    const observer=typeof ResizeObserver!=="undefined"?new ResizeObserver(resize):null;
    if(observer)observer.observe(viewport);else root.addEventListener("resize",resize);
    resize();fit();
    viewport.addEventListener("wheel",e=>{e.preventDefault();const r=viewport.getBoundingClientRect();if(view.scale<.12&&e.deltaY<0)openOverview(e.clientX-r.left,e.clientY-r.top);
      else{view=zoomAt(view,clamp(view.scale*Math.exp(-e.deltaY*.0015),.004,5),e.clientX-r.left,e.clientY-r.top);queue();}},{passive:false});
    const touches=new Map();
    viewport.addEventListener("pointerdown",e=>{viewport.setPointerCapture(e.pointerId);touches.set(e.pointerId,{x:e.clientX,y:e.clientY});pointer={x:e.clientX,y:e.clientY,moved:false};});
    viewport.addEventListener("pointermove",e=>{if(touches.has(e.pointerId)){const old=touches.get(e.pointerId);touches.set(e.pointerId,{x:e.clientX,y:e.clientY});const values=[...touches.values()];if(values.length===2){const distance=Math.hypot(values[0].x-values[1].x,values[0].y-values[1].y);if(pinch){if(pointer)pointer.moved=true;const r=viewport.getBoundingClientRect();const cx=(values[0].x+values[1].x)/2-r.left,cy=(values[0].y+values[1].y)/2-r.top;
          if(view.scale<.12&&distance>pinch*1.05)openOverview(cx,cy);
          else{view=zoomAt(view,clamp(view.scale*distance/pinch,.004,5),cx,cy);queue();}}pinch=distance;}else if(pointer){view={...view,x:view.x+e.clientX-old.x,y:view.y+e.clientY-old.y};if(Math.hypot(e.clientX-pointer.x,e.clientY-pointer.y)>4)pointer.moved=true;queue();}return;}
      if(useCanvas){const r=viewport.getBoundingClientRect(),i=hitTest(nodes,view,e.clientX-r.left,e.clientY-r.top);if(i!==hovered){hovered=i;if(i>=0)show(i);else if(selected>=0)show(selected);}}
    });
    viewport.addEventListener("pointerup",e=>{const was=pointer;touches.delete(e.pointerId);if(touches.size<2)pinch=null;if(!touches.size)pointer=null;if(was&&!was.moved){const r=viewport.getBoundingClientRect();
      if(useCanvas&&view.scale<.12){
        const layers=[...byLayer.keys()].sort((a,b)=>a-b), column=Math.round((e.clientX-r.left)* (layers.length+1)/width)-1;
        if(column>=0&&column<layers.length)openOverview(e.clientX-r.left,e.clientY-r.top);
      }else choose(hitTest(nodes,view,e.clientX-r.left,e.clientY-r.top));}});
    viewport.addEventListener("pointercancel",e=>{touches.delete(e.pointerId);pointer=null;pinch=null;});
    viewport.addEventListener("keydown",e=>{if(e.target!==viewport)return;const step=40;if(e.key==="ArrowLeft")view.x+=step;else if(e.key==="ArrowRight")view.x-=step;else if(e.key==="ArrowUp")view.y+=step;else if(e.key==="ArrowDown")view.y-=step;else return;e.preventDefault();queue();});
    return {fit, destroy:()=>{if(observer)observer.disconnect();else root.removeEventListener("resize",resize);}};
  }
  root.OpGraph={mount,geometry};
})(typeof window === "undefined" ? null : window);
