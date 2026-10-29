# Python API

`opulse.World` gives Python access to an operator set, its expressions, traces, benchmark tasks
and fill in the blank problems. Evaluation uses the reference interpreter. Complete traces are
checked against it. Generation and task building use the same components and seeds as the
command line. Undefined values (NaN) are returned as `None`.

Every example on this page was run to produce the output shown below it
(`tools/api_examples.py` writes them).

## Grow a world

`World.grow` generates operators layer by layer. `layers` gives the number of new operators per
layer; the same arguments always give the same world, and the same operators as
`opulse operators --layers 20 10 5 --seed 1`.

--8<-- "docs/snippets/api_grow.md"

`atoms` chooses the starting set: `"integer"` (the default), `"atomic"`, a path to an operator
JSONL file, or a list of atom names, including atoms you registered
([Atoms](atoms.md)). `config` takes a YAML path, a dict or a `Settings` object. Keyword arguments
change single settings: a section as a dict (`recursion={"style": "direct"}`) or one key as
`section__key` (`semantics__bound=None`).

```python
world = opulse.World.grow(layers=[20, 10], seed=3, atoms="atomic")
world = opulse.World.grow(layers=[30], seed=0, operators={"symbol_sets": ["greek"]})
```

## Operators

`world.operators` lists the defined operators in the order they were made, `world.atoms` the
atomic operations and `world.layer(i)` one layer. `world["⊕"]` finds an operator by its symbol;
a symbol with several roles takes the role as a second key (`world["-", "prefix"]`).

--8<-- "docs/snippets/api_operator.md"

`evaluate` (or calling the operator) returns the value; `result` also returns the number of base
operations and calls, the cost measures of [Operators and definitions](definitions.md).
`table` evaluates a small grid of inputs:

--8<-- "docs/snippets/api_table.md"

## Traces

`op.trace(*args)` and `expression.trace()` reduce step by step, unfolding definitions leftmost
innermost, as in [Step by step solutions](step-by-step.md). Each step is checked against the
reference interpreter before the trace is returned. `depth`, `known` and `known_layers` set the
granularity; `trace.narrate("en")` gives the prose solution of datasets.

--8<-- "docs/snippets/api_trace.md"

## Expressions

`world.expression(text)` parses with the operators' priorities, like the expressions of generated
datasets. Variables are allowed and bound with `evaluate(a=..., b=...)`.

--8<-- "docs/snippets/api_expression.md"

`world.sample_expressions` samples exactly like `opulse expressions`, with the same options
(`depth`, `frequency`, `max_layer`, `keep_undefined`, `cot`). Each result keeps its full dataset
record in `expr.record`.

--8<-- "docs/snippets/api_sample.md"

## Benchmark tasks and problems

`world.tasks(family, n, **options)` builds tasks like `opulse bench build` and accepts the
builder's options (`context`, `distractors`, `shuffle`, `max_depth`, `naming`, `answer_format`,
`operator_frequency`, and the others). By default it rederives every answer from its prompt text,
as `opulse bench check` does, and fails if one does not follow. `tasks.to_jsonl(path)` writes the
file the benchmark commands read.

--8<-- "docs/snippets/api_tasks.md"

`world.holes` makes fill in the blank problems with checked solution sets
([Solving for unknowns](solving.md)). `world.equivalent` checks whether two expressions agree on
every input. A `proved` verdict covers all inputs; a `bounded` verdict covers only tested inputs.
`world.equivalences()` lists candidate operator pairs and their verdicts
([Laws and equivalence](properties.md)).

--8<-- "docs/snippets/api_holes.md"

--8<-- "docs/snippets/api_equivalence.md"

## Save and load

`world.save(path)` writes a directory with `operators.jsonl` (the file `opulse operators` writes),
`config.yaml` and `world.json`. Every command line tool reads the first two. `World.load` reads
such a directory or a plain operator JSONL file.

--8<-- "docs/snippets/api_save.md"

## Dependencies

`world.dependencies(op)` lists the operators a definition calls, `transitive=True` all of them;
`op.callers` lists the operators that call it. `world.graph()` draws the dependency graph, and
`world.graph(focus=op)` only what `op` needs.

--8<-- "docs/snippets/api_dependencies.md"

## In a notebook

Worlds, operators, expressions, traces, tasks and graphs display themselves in Jupyter. The views
use inline styles only and follow the colours of these pages: cyan for composition, amber for
branching, magenta for recursion. They are shown below exactly as a notebook renders them.

A world shows its operators per layer and kind; the layers open to list the definitions:

--8<-- "docs/snippets/api_view_world.html"

An operator shows its definition, kind, layer, the operators it calls and a table of values:

--8<-- "docs/snippets/api_view_operator.html"

A trace marks the subexpression each step rewrites, in the colour of its operator, and says why:

--8<-- "docs/snippets/api_view_trace.html"

A task shows its definitions, expression and answer; the full prompt opens below them:

--8<-- "docs/snippets/api_view_task.html"

A graph places every operator one column right of its deepest callee. Arrows point from a caller
to what it calls, and a loop marks recursion. Hover a node to read its definition.

--8<-- "docs/snippets/api_view_graph.html"

## Syntax colouring

Opulse ships a [Pygments](https://pygments.org) lexer, registered under the name `opulse`. Any
Pygments based tool colours Opulse code once the package is installed, including code blocks
marked `opulse` in Markdown. These pages use it:

```opulse
a ⊕ b = { a + (b @), if a >= 10 and not b == 0; NaN, else }
```

`world.lexer()` returns a lexer configured for one world: its parameter names, its spelling of NaN
and its numeral base markers.

--8<-- "docs/snippets/api_lexer.md"

The lexer never fails: any run of symbol characters is one operator, and any character it does not
know is plain text. Its options are `parameters`, `nan`, `words` (operator names that are words,
such as benchmark aliases), `markers` and `equals`.

## Reference

::: opulse.api.World
    options:
      show_root_heading: true
      members_order: source
      heading_level: 3

::: opulse.api.Op
    options:
      show_root_heading: true
      members_order: source
      heading_level: 3

::: opulse.api.Expression
    options:
      show_root_heading: true
      heading_level: 3

::: opulse.api.Trace
    options:
      show_root_heading: true
      heading_level: 3
