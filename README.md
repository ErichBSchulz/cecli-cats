# Cecli Atomic Tests

## Getting started

Follow the instructions in the README in the main `cecli` repo.

This means you'll want to clone this repo, probably into the a
`tmp-benchmarsks`.

```bash
cd MAIN_CECLI_DIR
mkdir -p tmp-benchmarsks # if not already clone
cd -p tmp-benchmarsks # if not already clone
git clone https://github.com/ErichBSchulz/cecli-cats cecli-cats
```

Use `uv` to install the `cecli-cat` script:

```bash
cd cecli-cats
# Use --force to overwrite any existing installation
uv tool install --force .
cecli-cat --help
```

If you are developing `cecli-cats`, use `-e` (editable) so changes take effect
immediately:

```bash
uv tool install -e .
```

## Contributing

### Atomic results

Yes please!

```bash
# set $C to your name to get credit
C=anon
# set $B to your bencmark file dir
B=/path/to/your/tmp.tmp-benchmarks
# then ideally:
tar -cvzf cat_full.$C.tar.gz -C "$B" .
# or, **alternatively** (only grab the resultss files):
find "$B" -name ".aider.results.json" -print0 | tar --null -cvzf cat_results.$C.tar.gz --files-from -
```

### New CATS ("excercises")

As the tests get saturated we need new and novel tests.

### New metrics

Yes! We need metrics that move beyond pass/fail on coding tasks. This will need
some thought.

## Why test?

Its very hard to improve what you cannot measure.

Benchmarking enables us to chose the best model for our needs, and configure it
to get the best out of it.

As models evolve, so must our tests and our metrics.

Cecli Atomic Tests (Cats) aim to enable us to tune hyper-parameters and cecli
settings.

The proposed changes enable approaching a new set of more nuanced questions:

- "Which prompt is best?"
- "How do we get the best performance from a specific model (x model)?"
- "Which tests are best at discriminating certain optimisations?"

## Filing conventions

* All individual test runs live in a directory matching `YYYY-MM-DD-HH-MM-SS*`
* Classic runs will have individual test runs in a folder `LANGUAGE/exercises/practice`,
  where LANGUAGE is one of a defined set.
* New CAT test runs live a directory named after a hash of its contents and
  also all have a cat.yaml file.

## Source Attribution

This is a fork of the [Aider polyglot benchmark](), based on a subset of
repository contains a curated collection of programming exercises extracted from
Exercism's language tracks. These exercises are used for benchmarking and
testing purposes.

For more information see:

- [The aider blog](https://aider.chat/2024/12/21/polyglot.html)
- [The benchmark harness README](https://github.com/Aider-AI/aider/tree/main/benchmark)

All exercises in this repository are sourced from the following Exercism
language tracks:

[C++](https://github.com/exercism/cpp), [Go](https://github.com/exercism/go),
[Java](https://github.com/exercism/java),
[JavaScript](https://github.com/exercism/javascript),
[Python](https://github.com/exercism/python),
[Rust](https://github.com/exercism/rust)

All exercise content is copyright © [Exercism](https://exercism.org). These
exercises are used in accordance with Exercism's open source licenses.

Please visit [Exercism](https://exercism.org) or the repos above to see
licensing of these coding exercises.
