# Operator skeletons

An operator skeleton keeps the definition tree and replaces every atom application with a typed hole. A hole records its arity, parameter types, result type, and an optional role such as `predicate`. The tree retains substitutions, branch order, condition expressions, recursion form and bound, search bounds, and calls to other skeletons. The `source_correspondence` field records the original atoms separately from the holes. Its structural hash ignores atom identities and value type names. Each skeleton also has an ID, so two operators with the same structure can remain separate records in one set.

A correspondence binds each hole to a registered atom in a target world. `int` can map to another registered type through a type map; `bool` can stay `bool`. The target atom must have the mapped parameter and result types and the same arity. A unary atom may use a different written position. Literals and comparison operators remain in the tree, so a type map must leave those expressions valid.

An instance is accepted only after type checking, compilation, reference agreement, the generator checks, and sampled definedness and output variety checks. Search uses a seed. If no correspondence passes within the attempt limit, the command reports the last rejection. Operators are built in dependency order, and each instance record links its operator ID to the skeleton ID.

## Extract and instantiate

This example grows one integer operator and extracts its skeleton. The commands below produced the shown output in a local run.

```console
$ opulse operators --preset integer --out /tmp/source.jsonl --layers 1 --proportions 1 0 0 --seed 8
{
  "accepted": {
    "simple_definition": 1
  },
  "rejected": {},
  "layers": {
    "0": 1
  }
}
$ opulse skeleton extract --operators /tmp/source.jsonl --out /tmp/skeletons.json
{"skeletons": 1, "out": "/tmp/skeletons.json"}
```

This example creates an atom file and binds the extracted skeleton to that world.

```console
$ opulse operators --preset integer --out /tmp/integer_atoms.jsonl --layers 0 --seed 8
{
  "accepted": {},
  "rejected": {},
  "layers": {}
}
$ opulse skeleton instantiate --skeletons /tmp/skeletons.json --atoms /tmp/integer_atoms.jsonl --world integer --out /tmp/integer_instance.jsonl --seed 3
{"world": "integer", "instances": 1, "operators": "/tmp/integer_instance.jsonl", "records": "/tmp/integer_instance.instances.jsonl"}
```

`--type-map` reads a JSON object such as `{"str": "list[int]"}`. `--correspondence` reads a JSON object whose keys have the form `skeleton_id:hole_id` and whose values are target atom function IDs. An explicit correspondence fixes selected holes while search fills the others.

For a registered value type without a built in probe sampler, `--sample-values` reads a JSON object that maps each target type to a nonempty list of values. For `match`, the same option reads an object keyed first by world name and then by target type.

## Match worlds

This example instantiates one skeleton in the integer preset and the extended integer atom set, then checks that the structures and composition depths agree while the sampled result tables differ.

```console
$ opulse atoms export --set integer --out /tmp/extended_atoms.jsonl
$ opulse skeleton match --skeletons /tmp/skeletons.json --world integer=/tmp/integer_atoms.jsonl --world extended=/tmp/extended_atoms.jsonl --out-dir /tmp/matched --seed 3 --attempts 30
```

This command searches for checked instances in two atom sets and writes a comparison report.

The directory contains one operator JSONL file per world, `instances.jsonl` with the hole correspondences, and `match.json` with the comparisons. For other registered worlds, pass their atom JSONL files with further `--world` options. `--type-maps` reads a JSON object keyed by world name, with a type map for each world.

## Benchmark splits

This example builds tasks from a matched instance. Each task has `skeleton_ids`, a singular `skeleton_id` when exactly one skeleton is needed, and `world`.

```console
$ opulse bench build --operators /tmp/matched/integer.jsonl --out /tmp/integer_tasks.jsonl --count 5 --max-answer-share 1.0 --seed 4
wrote 5 compute tasks to /tmp/integer_tasks.jsonl (answers re-derived from the prompts)
```

Build tasks from each world, combine the JSONL files, then use `opulse bench split --tasks combined.jsonl --out-dir splits --by skeleton` to keep every shared skeleton in one split. Use `--by world` to keep every world in one split. Tasks that depend on multiple skeletons stay together with every task sharing any of those skeletons. `opulse bench leakage --train-tasks splits/train.jsonl --test-tasks splits/test.jsonl` reports shared skeleton and world IDs.

A transfer experiment can train on some worlds and test the same skeletons in another world, or train on some skeletons and test unseen structures in each world. The instance records identify the corresponding definitions, and the split report makes shared structure visible.

## Correspondence evidence

Every instance record and match comparison states a grade. G1 means that each bound atom has the mapped parameter types, result type, and arity. G2 means that both atom sets satisfy every equation supplied for the comparison on the declared finite domains. The supported equations are `associativity`, `commutativity`, `identity`, `absorbing`, `involution`, `idempotence`, and `inverse_pair`. An identity or absorbing equation supplies `source_element` and `target_element`. An inverse pair supplies the other source atom ID in `other`. The report lists the result for each equation and labels the method `bounded exhaustive`.

G3 means that a bijection of the declared finite value domains commutes with every mapped atom on every input tuple. The report includes the bijection. If a needed domain is absent, its sizes differ, or the search limit is reached, the report says `not established` and retains G1 or G2. This is a claim about the declared domains only. Use `--partial-domains` to treat outputs outside those domains as undefined in both restricted algebras. For example, a domain containing the empty string and `a` can correspond to the empty list and `[1]` under concatenation, length, tail, and equality when concatenations outside that domain are excluded in both worlds.

The following files declare finite domains and two equations for one mapped addition atom.

```json
{"integer": {"int": [0, 1, 2]}, "rotation": {"int": [0, 1, 2]}}
```

```json
[{"atom": "SOURCE_ATOM_ID", "law": "associativity"}, {"atom": "SOURCE_ATOM_ID", "law": "commutativity"}]
```

Pass the first file with `--grade-domains` and the second with `--equations`. Without these files, a matched pair receives G1.

## Matched probes

Each instance record contains a `probe` object with 16 sampled inputs, the undefined rate, all unfolded trace lengths, and their mean `unfolded_length`. The trace counts individual reduction steps at the finest granularity. A compute benchmark task built from a matched instance records its own exact `axes.unfolded_length` for the expression in that task. For other operator sets, pass `--unfolded-length` to record the axis. A truncated trace records `null` for that axis.

The match command accepts `--nan-tolerance` for the largest difference in undefined rates and `--length-tolerance` for the largest unfolded length difference on any paired probe. Supplying either option turns on probe matching. Search uses the seed and reports counts by rejection reason in `match.json`. For example, `--nan-tolerance 0.05 --length-tolerance 2` accepts a pair only when both differences fit those limits. The example permits at most five percentage points of undefined rate difference and two trace steps on each paired probe.

For different value types, supply equal length, correspondingly ordered `--sample-values` lists for each world to align probe inputs.

## Weighted worlds

The following command builds ten checked benchmark tasks with five from each named world.

```console
$ opulse bench build --world strings=/tmp/strings.jsonl --world lists=/tmp/lists.jsonl --world-mix strings:0.5,lists:0.5 --count 10 --out /tmp/mixed_tasks.jsonl --max-answer-share 1
```

Each task records its world. A seeded schedule allocates counts by largest remainder and shuffles the order. The optional `--world-settings` JSON file has one object per world. Each object can name a `config` file, an `operator_frequency`, a `frequency_seed`, and `skeleton_weights` keyed by skeleton ID. A skeleton weight multiplies the sampling weight of its defined operators within that world.

The following command writes a mixed corpus and records `world` beside the text of every item in `mixture.jsonl`.

```console
$ opulse corpus --operators strings=/tmp/strings.jsonl --operators lists=/tmp/lists.jsonl --world-mix strings:0.5,lists:0.5 --documents 100 --out /tmp/mixed_corpus
```

Each world also has its own checked corpus and manifest under `worlds/NAME`. The same `--world-settings` file applies to corpus generation, including its configuration file and skeleton weights for expression sampling.

## Skill world adapter

`opulse.skeleton_adapter.SkillWorldAdapter` defines the bridge for a world with its own skill simulator. It supplies atom signatures, builds a skill from a skeleton tree and hole bindings, runs the skill on probe inputs, and supplies values for each parameter type. `instantiate_skills` checks signatures and simulator results and records G1 plus probe measurements. This branch contains no adapter for the action world's `Skill` class and `run_skill` simulator.
