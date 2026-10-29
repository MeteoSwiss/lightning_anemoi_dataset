# template-anemoi-dataset

This repository serves as a template for creating Anemoi datasets. The motivation for creating separate repositories for different datasets, as opposed to a single repository containing all dataset recipes, is to maintain clear boundaries between different data sources and their respective processing logic, and to facilitate independent versioning and reproducibility.

# Table of contents
1. [Using this template](#using-this-template)
2. [Development guidelines](#development-guidelines)
3. [Versioning guidelines](#versioning-guidelines)


# Using this template

Each instantiation of this template targets a **single data source**. The repo is named:

```
<source>-anemoi-dataset
```

For example: `ich1-analysis-anemoi-dataset`, `synop-anemoi-dataset`, `mtg-anemoi-dataset`.

Within one repo, **variants** represent different configurations of the same source: different sets of variables, vertical coordinates, resolutions, time granularity, etc. 

## Granularity boundary: repo vs variant

The boundary rule is:

> **New repo** when the data comes from a different source system.
> **New variant** when the difference is a configuration choice within the same source system.

Use a new repo if *any* of these are true:

- Different data source
- Different data access system
- Different domain knowledge required to process the data

Use a new variant if *all* of these are true:

- Same data source
- Same data access system
- Same domain knowledge required to process the data
- Configs differ mainly in data queries (e.g. which variables, levels, or time ranges are selected) and processing

## Quickstart

* Instantiate this template directly from GitHub (button on the top right).
* Clone your repository, install the python environment with `uv sync`.
* Move this README somewhere else and rename `README.template.md` to `README.md`. 
* Get started developing and follow the instructions below.

# Development guidelines

## Writing dataset recipes

Dataset names follow the [anemoi-datasets naming conventions](https://anemoi.readthedocs.io/projects/datasets/en/latest/building/naming-conventions.html).

```
purpose-content-source-resolution-start-year-end-year-frequency-version[-extra-str]
```

- All lowercase
- Only letters, numbers, and dashes `-` are allowed
- No underscores `_`, no dots `.`, no uppercase, no special characters (`@`, `#`, `*`, etc.)
- Parts are separated by dashes `-`

| Component | Description | Examples |
|-----------|-------------|---------| 
| **purpose** | Intended use of the dataset | `varda`, `aifs`, `bris` |
| **content** | Data content, optionally `class-type-stream-expver` | `od-an-oper-0001` |
| **source** | Origin of the data | `mars`, `fdb`, `dwh` |
| **resolution** | Spatial resolution | `n320`, `1km`, `100m`, `NA` |
| **start-year** | Year of the first validity time | `1979` |
| **end-year** | Year of the last validity time | `2022` |
| **frequency** | Temporal resolution | `1h`, `6h`, `10m` |
| **version** | Version of the dataset content (which variables, levels, etc.) — must be prefixed with `v`. Bumped only when the dataset content changes in a breaking way. | `v1`, `v5` |
| **extra-str** *(optional)* | Additional information for experimental datasets | `recentered-on-oper` |


## Writing plugins or new anemoi features

When the functionality needed to generate a dataset is missing from anemoi, there are two options.

* Implement this functionality as a _plugin_
* Implement this functionality in anemoi itself (usually in anemoi-datasets) 

To facilitate working on new functionality for a new dataset, both `anemoi-plugins-meteoswiss` and `anemoi-datasets` have been in included here as git submodules under `packages/`. If you are not familiar with git submodules, ask your favourite LLM. In short, your master repository tracks _pointers_ to the specific commits of the submodules, allowing you to control which version of the submodule is used. If you are developing a new dataset and need to implement a feature in a submodule, do this:

* create a new branch in the master repository 
* create a new branch in the submodule, make your changes and commit them
* update the pointer in the master repository to point to the new commit in the submodule (`git add <submodule>` and `git commit -m "Update submodule pointer"`)
* (optional) update `branch` in the `.gitmodules` file to track a remote branch for the submodule


# Versioning guidelines

A dataset is a reproducible build artifact. Its exact content is determined by:

1. **The recipe** – the YAML configuration file under `config/` passed to `anemoi-datasets`.
2. **The code** – the pinned commits of the `anemoi-datasets` and `anemoi-plugins-meteoswiss`
   submodules, plus any project-level source code.

Both must be versioned together. A Git tag on this repository captures all of this in a single,
immutable reference. **The tag must be created before running a production dataset generation.**

A git tag will have the same version as the version part in the dataset name. For instance

```
purpose-content-source-resolution-start-year-end-year-frequency-v1
```

will get a tag `v1`. 

Optionally, multiple variants of a dataset can be generated. A variant of a dataset will typically be identified by the **extra-str** part of the dataset name. Information about the variant must then be included in the git tag. For instance

```
purpose-content-source-resolution-start-year-end-year-frequency-v1-pl13
```

will get a tag `v1-pl13`. If the variant information is encoded in something else (e.g. a different resolution), you may also use that instead.

After you have generated a new dataset and pushed a corresponding tag, you can create a GitHub release, with a description. If the data is publicly available, include a link.