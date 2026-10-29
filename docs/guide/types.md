# Typed values

Opulse supports integers, booleans, strings, lists of integers, and the undefined value `NaN`. Each atom and operator records the type of every parameter and its result. A definition is checked when it is generated or interpreted. A condition can use a boolean expression directly.

The `strings` preset includes concatenation, length, reversal, first character, removal of the first character, letter case conversion, and equality. This operator joins two strings and then converts the result to uppercase:

```text
a ◇ b = { (a ⊕ b) ⇧ }
```

The `lists` preset includes construction, head, tail, length, append, sum, indexed access, and equality. This operator joins two lists and removes the first element:

```text
a ♤ b = { (a ⊞ b) ⌄ }
```

String literals use quotes, as in `"ab"`. List literals use brackets, as in `[1, 2]`. The strings `true` and `false` are boolean literals. An empty list has type `list[int]` when it occurs in these presets. A base operation with an undefined argument gives `NaN`.

The `operators` command accepts `strings` and `lists` as preset values. The `expressions`, `verify`, and `bench build` commands read the value types from the operator file. Benchmark prompts state the type of each generated operator, and the prompt check parses those signatures before recomputing an answer.

Set `semantics.max_string_length` and `semantics.max_list_length` in a configuration file to limit the result of each base operation. Both default to 256. A result beyond its limit gives `NaN`. The integer bound remains controlled by `semantics.bound`.

The z3 encoder represents strings with string expressions and integer lists with sequence expressions when an atom has an encoding. Atoms such as letter case conversion and list sum have no z3 encoding and are reported as unavailable to the solver.

The integer solver export leaves typed operators without an exported formula.
