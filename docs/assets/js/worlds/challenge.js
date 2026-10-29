(function () {
  "use strict";
  const W = window.OpulseWorlds;
  const motionReduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
  const short = (renderer, value) => renderer.shorten ? renderer.shorten(value) : value;
  const valueKey = value => JSON.stringify(value);

  function render(container, data, ctx) {
    const {tr, renderer, draw, element, rich} = ctx;
    const puzzles = data.challenge.challenges;
    const root = element("section", "owc");
    const picker = element("nav", "owc-picker");
    picker.setAttribute("aria-label", tr("Choose a puzzle", "选择谜题"));
    const card = element("div", "owc-card");
    root.append(picker, card);
    container.replaceChildren(root);
    let timer = null;
    const stop = () => { if (timer !== null) clearTimeout(timer); timer = null; };
    root.addEventListener("ow:close", stop);
    function solved(id) {
      try { return localStorage.getItem("ow-world-challenge:" + data.world + ":" + id) === "1"; }
      catch (error) { return false; }
    }
    function save(id) {
      try { localStorage.setItem("ow-world-challenge:" + data.world + ":" + id, "1"); }
      catch (error) { /* storage is optional */ }
    }
    function heading(text) { return element("h3", "owc-heading", text); }
    function textFor(record, key) { return tr(record[key], record[key + "_zh"] || record[key]); }
    function expression(text) {
      const node = element("code", "owc-expression");
      node.innerHTML = rich(short(renderer, text));
      node.title = text;
      return node;
    }
    function changedText(before, after) {
      let first = 0;
      while (first < before.length && first < after.length && before[first] === after[first]) first++;
      let last = 0;
      while (last < before.length - first && last < after.length - first &&
             before[before.length - 1 - last] === after[after.length - 1 - last]) last++;
      if (first === after.length) return rich(after);
      return rich(after.slice(0, first)) + "<mark>" + rich(after.slice(first, after.length - last)) +
        "</mark>" + rich(after.slice(after.length - last));
    }
    function ruleRow(rule, variant) {
      const row = element("div", "owc-rule" + (variant ? " is-changed" : ""));
      row.append(element("span", "owc-symbol", rule.symbol));
      const copy = element("div", "owc-rule-copy");
      const atom = !variant && data.atoms?.some(item => item.symbol === rule.symbol);
      if (atom || (!variant && rule.text === rule.plain)) {
        copy.append(element("span", "owc-rule-plain", textFor(rule, "plain")));
        if (atom) copy.append(element("small", "owc-atom", tr("atom", "原子操作")));
      } else {
        const definition = element("code", "owc-rule-text");
        definition.innerHTML = variant ? changedText(short(renderer, variant.before), short(renderer, variant.after)) :
          rich(short(renderer, rule.text));
        copy.append(definition);
        if (variant) copy.append(element("small", "owc-was", tr("was ", "原为 ") + short(renderer, variant.before)));
        copy.append(element("span", "owc-rule-plain", variant ?
          tr(variant.plain_after, variant.plain_after_zh || variant.plain_after) : textFor(rule, "plain")));
      }
      row.append(copy);
      return row;
    }
    function steps(record, stage, done, question) {
      const trace = record.steps || [];
      const operator = data.operators?.find(item => question.expression.includes(item.name));
      const example = operator && {operator: operator.name, expression: question.expression, inputs: question.inputs};
      stage.hidden = false;
      stage.replaceChildren(heading(tr("Checked derivation", "已核验的推导")));
      const host = element("div", "owc-step-view");
      const visual = element("div", "owc-step-visual");
      const result = element("div", "owc-result");
      result.append(heading(tr("Result", "结果")), element("div", "owc-result-visual"));
      stage.append(host, visual, result);
      const rows = trace.map((step, i) => ({...step, expr_before: i ? trace[i - 1].expr : question.expression,
        expr_after: step.expr, rule: tr(step.rule, step.rule_zh || step.rule),
        kind: step.kind || (step.rule ? "expand" : "eval")}));
      const formatted = text => { const node = document.createElement("span"); node.innerHTML = rich(short(renderer, String(text))); return node; };
      window.OpulseStepView.render(host, {steps: rows, page_size: 50,
        lang: (document.documentElement.lang || "").startsWith("zh") ? "zh" : "en", renderValue: formatted,
        labels: {describe: step => {
          const label = formatted(step.rule);
          if (step.rule) window.OpulseAtoms.title(label, data.world, step.rule);
          return label;
        }, onSelect: (step, position) => {
          visual.replaceChildren();
          let previous = question.inputs[0], latest = previous;
          for (let i = 0; i <= position; i++) if (trace[i]?.value) { previous = latest; latest = trace[i].value; }
          try {
            if (renderer.renderStep && data.world !== "action" && data.world !== "pitch") renderer.renderStep(visual,
              {...step, expression: step.expr, value: latest, previous},
              {...data, data, world: data, operator, example, steps: trace, index: position,
                stepIndex: position, compact: true, mini: true});
            else draw(visual, latest, renderer, {...data, compact: true, mini: true});
            if (!visual.childNodes.length) draw(visual, latest, renderer, {...data, compact: true, mini: true});
          } catch (error) { draw(visual, latest, renderer, {...data, compact: true, mini: true}); }
        }}});
      draw(result.querySelector(".owc-result-visual"), record.answer, renderer, {...data, compact: true, mini: true});
      done();
    }
    function choices(record, stage, question, complete) {
      const options = element("div", "owc-options");
      options.setAttribute("role", "group");
      options.setAttribute("aria-label", tr("Predict the result", "预测结果"));
      const feedback = element("p", "owc-feedback");
      feedback.setAttribute("role", "status");
      const reveal = element("div", "owc-reveal");
      reveal.hidden = true;
      record.options.forEach((value, index) => {
        const button = element("button", "owc-option");
        button.type = "button";
        const accessible = value && typeof value.v === "object" ? JSON.stringify(value.v) : W.valueText(value);
        button.setAttribute("aria-label", tr("Choice ", "选项 ") + (index + 1) + ": " + accessible);
        draw(button, value, renderer, {...data, compact: true, mini: true});
        button.onclick = () => {
          if (options.dataset.answered) return;
          options.dataset.answered = "1";
          const right = valueKey(value) === valueKey(record.answer);
          button.classList.add(right ? "is-right" : "is-wrong");
          button.setAttribute("aria-label", button.getAttribute("aria-label") + " — " + tr(right ? "correct" : "incorrect", right ? "正确" : "错误"));
          [...options.children].forEach(choice => { choice.disabled = true; });
          feedback.classList.toggle("is-right", right);
          feedback.textContent = right ? tr("Correct.", "答对了。") :
            tr("Not quite. ", "还不对。") +
            (tr(record.option_notes?.[index], record.option_notes_zh?.[index] || record.option_notes?.[index]) ||
              tr("Follow the steps to see the result.", "请看推导过程。"));
          steps(record, reveal, () => complete(right), question);
        };
        options.append(button);
      });
      stage.append(options, feedback, reveal);
    }
    function valueCard(value, label) {
      const slot = element("figure", "owc-induce-value");
      draw(slot, value, renderer, {...data, compact: true, mini: true});
      if (label) slot.append(element("figcaption", "", label));
      return slot;
    }
    function inputCards(inputs) {
      const group = element("div", "owc-induce-inputs");
      inputs.forEach((value, n) => group.append(valueCard(value,
        inputs.length > 1 ? tr("Input ", "输入 ") + (n + 1) : "")));
      return group;
    }
    function induce(puzzle, index) {
      card.append(heading(tr("Guess the rule", "猜规律")));
      const atomLegend = element("div", "owc-atoms-legend");
      card.append(atomLegend);
      window.OpulseAtoms.legend(atomLegend, data.world, puzzle.reference_definition?.text || "");
      const examples = element("div", "owc-induce-examples");
      puzzle.examples.forEach(example => {
        const pair = element("div", "owc-induce-pair");
        pair.append(inputCards(example.inputs), element("span", "owc-induce-arrow", "→"),
          valueCard(example.output, ""));
        examples.append(pair);
      });
      card.append(examples, heading(tr("What comes out?", "结果是什么？")));
      const query = element("div", "owc-induce-query");
      query.append(inputCards(puzzle.query.inputs), element("span", "owc-induce-arrow", "→ ?"));
      card.append(query);
      const options = element("div", "owc-options");
      options.setAttribute("role", "group");
      options.setAttribute("aria-label", tr("Predict the result", "预测结果"));
      const feedback = element("p", "owc-feedback");
      feedback.setAttribute("role", "status");
      const reveal = element("div", "owc-induce-reveal");
      reveal.hidden = true;
      puzzle.query.options.forEach((value, n) => {
        const button = element("button", "owc-option");
        button.type = "button";
        button.setAttribute("aria-label", tr("Choice ", "选项 ") + (n + 1) + ": " +
          (value && typeof value.v === "object" ? JSON.stringify(value.v) : W.valueText(value)));
        draw(button, value, renderer, {...data, compact: true, mini: true});
        button.onclick = () => {
          if (options.dataset.answered) return;
          options.dataset.answered = "1";
          const right = valueKey(value) === valueKey(puzzle.answer);
          button.classList.add(right ? "is-right" : "is-wrong");
          [...options.children].forEach(choice => {
            choice.disabled = true;
            if (valueKey(puzzle.query.options[[...options.children].indexOf(choice)]) === valueKey(puzzle.answer))
              choice.classList.add("is-right");
          });
          feedback.classList.toggle("is-right", right);
          feedback.textContent = right ? tr("Correct.", "答对了。") :
            tr("Look at the rule and try the examples again.", "请对照规则再看一遍例子。");
          reveal.hidden = false;
          reveal.append(heading(tr("Rule", "规则")),
            element("code", "owc-expression", short(renderer, puzzle.reference_definition.text)),
            element("p", "owc-induce-plain", textFor(puzzle.reference_definition, "plain")),
            element("p", "owc-why", textFor(puzzle, "why")));
          if (right) {
            save(puzzle.id);
            picker.children[index].classList.add("is-solved");
            picker.children[index].setAttribute("aria-label", tr("Puzzle ", "谜题 ") + (index + 1) +
              tr(", solved", "，已解答"));
          }
        };
        options.append(button);
      });
      card.append(options, feedback, reveal);
    }
    function select(index) {
      stop();
      const puzzle = puzzles[index], question = puzzle.question;
      [...picker.children].forEach((chip, n) => chip.setAttribute("aria-current", n === index ? "true" : "false"));
      card.replaceChildren();
      card.append(element("span", "owc-level owc-level-" + puzzle.level, puzzle.level));
      if (puzzle.kind === "induce") { induce(puzzle, index); return; }
      const rules = element("div", "owc-rules");
      puzzle.rules.forEach(rule => rules.append(ruleRow(rule)));
      const atomLegend = element("div", "owc-atoms-legend");
      card.append(heading(tr("Rules", "规则")), rules, atomLegend, heading(tr("Question", "题目")), expression(question.expression));
      window.OpulseAtoms.legend(atomLegend, data.world,
        puzzle.rules.map(rule => rule.text).concat([question.expression, puzzle.variant?.after || ""]));
      const inputs = element("div", "owc-inputs");
      question.inputs.forEach((value, n) => {
        const slot = element("figure", "owc-input");
        draw(slot, value, renderer, {...data, compact: true});
        slot.append(element("figcaption", "", tr("Input ", "输入 ") + (n + 1)));
        inputs.append(slot);
      });
      card.append(inputs, heading(tr("Predict", "预测")));
      const first = element("div", "owc-stage");
      const variantStage = element("div", "owc-variant");
      variantStage.hidden = true;
      const why = element("p", "owc-why");
      why.hidden = true;
      why.textContent = textFor(puzzle, "why");
      card.append(first, why, variantStage);
      choices(puzzle, first, question, firstRight => {
        const variant = puzzle.variant;
        why.hidden = false;
        variantStage.hidden = false;
        variantStage.append(heading(tr("Change one rule", "改变一条规则")),
          ruleRow(puzzle.rules[variant.rule_index], variant),
          element("p", "owc-again", tr("Predict the result with this rule.", "按新规则再次预测结果。")));
        choices(variant, variantStage, question, variantRight => {
          if (firstRight && variantRight) {
            save(puzzle.id);
            picker.children[index].classList.add("is-solved");
            picker.children[index].setAttribute("aria-label", tr("Puzzle ", "谜题 ") + (index + 1) + tr(", solved", "，已解答"));
          }
        });
      });
    }
    puzzles.forEach((puzzle, index) => {
      const chip = element("button", "owc-chip owc-level-" + puzzle.level, String(index + 1));
      chip.type = "button";
      chip.classList.toggle("is-solved", solved(puzzle.id));
      chip.setAttribute("aria-label", tr("Puzzle ", "谜题 ") + (index + 1) + ", " + puzzle.level +
        (solved(puzzle.id) ? tr(", solved", "，已解答") : ""));
      chip.onclick = () => select(index);
      picker.append(chip);
    });
    select(0);
  }

  W.extend("*", {tabs: [{id: "challenge", label: "Challenge", label_zh: "挑战",
    available: data => !!data.challenge, render}]});
}());
