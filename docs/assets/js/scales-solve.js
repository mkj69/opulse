(function () {
  "use strict";
  var keys = ["s10", "s100", "s1000", "s10000"];
  var labels = ["≈10", "≈100", "≈1000", "≈10000"];
  function esc(value) {
    return String(value).replace(/[&<>"']/g, function (c) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"}[c];
    });
  }
  function operatorText(value, symbol) {
    var text = String(value);
    var parts = text.split(symbol);
    return parts.map(esc).join('<span class="op-sym">' + esc(symbol) + '</span>');
  }
  function init(root) {
    var zh = root.getAttribute("data-lang") === "zh";
    var base = root.getAttribute("data-base");
    var tr = function (en, cn) { return zh ? cn : en; };
    var tabs = root.querySelector(".ss-tabs");
    var panel = root.querySelector(".ss-panel");
    var cache = {};
    var active = 0;
    var frame = 0;
    var timer = null;
    var serial = 0;
    var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var observer = null;
    keys.forEach(function (key, index) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "ss-tab";
      button.id = root.id + "-tab-" + key;
      button.setAttribute("role", "tab");
      button.setAttribute("aria-controls", root.id + "-panel");
      button.textContent = labels[index];
      button.addEventListener("click", function () { select(index); });
      button.addEventListener("keydown", function (event) {
        var next = event.key === "Home" ? 0 : event.key === "End" ? 3 :
          event.key === "ArrowRight" ? (index + 1) % 4 :
          event.key === "ArrowLeft" ? (index + 3) % 4 : -1;
        if (next >= 0) { event.preventDefault(); select(next); tabs.children[next].focus(); }
      });
      tabs.appendChild(button);
    });
    function stop() { if (timer !== null) { clearInterval(timer); timer = null; } }
    function select(index) {
      stop();
      if (observer) { observer.disconnect(); observer = null; }
      active = index;
      frame = 0;
      serial += 1;
      var ticket = serial;
      Array.prototype.forEach.call(tabs.children, function (button, i) {
        button.setAttribute("aria-selected", i === index ? "true" : "false");
        button.tabIndex = i === index ? 0 : -1;
      });
      panel.setAttribute("aria-labelledby", tabs.children[index].id);
      panel.textContent = tr("Loading scale…", "正在加载规模…");
      var pending = cache[keys[index]] || fetch(base + keys[index] + ".json")
        .then(function (response) { if (!response.ok) { throw new Error("missing"); } return response.json(); });
      cache[keys[index]] = pending;
      Promise.resolve(pending).then(function (data) {
        if (serial !== ticket) { return; }
        cache[keys[index]] = data;
        if (reduced) { frame = Math.ceil(data.scan.length / 8) + data.reverse.length + 1; }
        render(data);
        if (!reduced) {
          if ("IntersectionObserver" in window) {
            observer = new IntersectionObserver(function (entries) {
              if (entries[0].isIntersecting) {
                observer.disconnect(); observer = null;
                panel.querySelector('[data-action="play"]').click();
              }
            }, { threshold: 0 });
            observer.observe(root);
          } else { panel.querySelector('[data-action="play"]').click(); }
        }
      }).catch(function () {
        if (serial === ticket) {
          panel.textContent = tr("This scale is available when its operator set finishes.",
            "该规模的运算符集完成后即可查看。");
        }
      });
    }
    function render(data) {
      var total = Math.ceil(data.scan.length / 8) + data.reverse.length + 1;
      if (frame > total) { frame = total; }
      var scanFrames = Math.ceil(data.scan.length / 8);
      var seen = Math.min(data.scan.length, frame * 8);
      var steps = Math.max(0, frame - scanFrames);
      var nf = new Intl.NumberFormat(zh ? "zh-CN" : "en-US");
      var stats = tr("Set", "集合") + ": " + nf.format(data.set_size) + " · " +
        tr("Target layer", "目标层") + ": " + data.target_layer + " · " +
        tr("Dependency closure", "依赖闭包") + ": " + nf.format(data.closure_size) + " · " +
        tr("Fully unfolded answer check", "答案完全展开检查") + ": " +
        nf.format(data.check_steps) + " " + tr("steps", "步") + " · " +
        tr("All candidate checks", "所有候选值检查") + ": " +
        nf.format(data.scan_steps) + " " + tr("steps", "步");
      var cells = data.scan.map(function (row, i) {
        var cls = "ss-cell ss-on" + (i === seen - 1 && frame <= scanFrames ? " ss-cursor" : "") +
          (data.hits.indexOf(row.x) >= 0 ? " ss-hit" : "") +
          (row.value === null ? " ss-undefined" : "");
        return '<span class="' + cls + '" title="x = ' + row.x + ': ' +
          esc(row.value === null ? tr("undefined", "未定义") : row.value) + ' · ' +
          nf.format(row.steps) + ' ' + tr("fully unfolded steps", "完全展开步数") + '"></span>';
      }).join("");
      var last = data.scan[Math.max(0, seen - 1)];
      var readout = frame === 0 ? tr("The reference interpreter tests every x in the stated domain.",
        "参考解释器逐个检验指定区间内的 x。") :
        frame <= scanFrames ? "x = " + last.x + " → " +
          (last.value === null ? tr("undefined", "未定义") : nf.format(last.value)) +
          " · " + nf.format(last.steps) + " " + tr("fully unfolded steps", "完全展开步数") :
          tr("Candidate scan complete; only the highlighted x gives the target.",
            "候选值扫描完成；只有高亮的 x 得到目标值。");
      var proof = data.reverse.slice(0, steps).map(function (row) {
        var known = Object.keys(row.known).map(function (key) {
          return tr("argument ", "参数 ") + (Number(key) + 1) + " = " + row.known[key];
        }).join(", ");
        return '<li>' + tr("Outside-in: ", "由外向内：") + '<code><span class="op-sym">' + esc(row.symbol) + '</span>' +
          '</code> ' + tr("must give", "须得到") + ' <strong>' + esc(row.target) +
          '</strong>' + (known ? ' (' + esc(known) + ')' : '') + '. ' +
          tr("The reference interpreter checks this input slot over ",
            "参考解释器在此区间逐个检查该输入位置：") + '[' + row.domain.join(", ") +
          ']. ' + tr("Matching input", "匹配的输入") + ' ∈ {' +
          row.candidates.map(esc).join(", ") + "}</li>";
      }).join("");
      var verdict = '<p class="ss-verdict"><strong>x = ' + data.answer +
        '</strong> · ' + tr("unique over", "在区间内唯一") + ' [' + data.domain.join(", ") +
        '] · ' + tr("forward check", "正向检查") + ': ' + nf.format(data.check_steps) +
        ' ' + tr("steps give", "步得到") + ' ' + esc(data.check_value) + '</p>';
      panel.innerHTML = '<div class="ss-stats">' + esc(stats) + '</div>' +
        '<div class="ss-equation"><code>' + operatorText(data.expression, data.target_operator).replace(/\bx\b/g, '<b class="ss-x">x</b>') +
        '</code> = <strong>' + esc(data.target) + '</strong></div>' +
        '<div class="ss-controls"><button type="button" data-action="prev" aria-label="' +
        tr("Previous step", "上一步") + '">◀</button><button type="button" data-action="play">' +
        (timer === null ? tr("Play", "播放") : tr("Pause", "暂停")) +
        '</button><button type="button" data-action="next" aria-label="' +
        tr("Next step", "下一步") + '">▶</button><input type="range" min="0" max="' + total +
        '" value="' + frame + '" aria-label="' + tr("Step", "步骤") + '"><span>' +
        frame + ' / ' + total + '</span></div>' +
        '<div class="ss-strip" aria-hidden="true">' + cells + '</div>' +
        '<div class="ss-axis"><span>' + data.window[0] + '</span><span>0</span><span>' +
        data.window[1] + '</span></div><p class="ss-readout" aria-live="polite">' +
        esc(readout) + '</p><ol class="ss-proof">' + proof + '</ol>' + verdict;
      var atomLegend = document.createElement("div");
      atomLegend.className = "ss-atoms-legend";
      panel.querySelector(".ss-equation").after(atomLegend);
      window.OpulseAtoms.legend(atomLegend, "integer", [data.expression].concat(data.reverse.map(function (row) { return row.symbol; })));
      panel.querySelector('[data-action="prev"]').disabled = frame === 0;
      panel.querySelector('[data-action="next"]').disabled = frame === total;
      panel.querySelector('[data-action="prev"]').onclick = function () { stop(); frame -= 1; render(data); };
      panel.querySelector('[data-action="next"]').onclick = function () { stop(); frame += 1; render(data); };
      panel.querySelector('[data-action="play"]').onclick = function () {
        if (timer !== null) { stop(); render(data); return; }
        if (frame === total) { frame = 0; }
        timer = setInterval(function () {
          frame += 1;
          if (frame >= total) { frame = total; stop(); }
          render(data);
        }, frame < scanFrames ? 300 : 900);
        render(data);
      };
      panel.querySelector('input[type="range"]').oninput = function (event) {
        stop(); frame = Number(event.target.value); render(data);
      };
    }
    select(0);
  }
  Array.prototype.forEach.call(document.querySelectorAll(".scales-solve"), init);
}());
