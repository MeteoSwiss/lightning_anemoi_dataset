# Name of the repository

Write a high level description of the dataset.

## Getting started

Write setup instructions such as the python virtual environment setup (ev. including uenv setup).

## Overview

* Describe the data source, including where it comes from, how it is accessed, and any relevant details about its structure or format.
* Describe, if any, the code needed to generate the dataset (preprocessing steps, anemoi plugins, etc.)
* Describe how to create a new dataset.

### Pre-generation checklist

Before generating a production dataset, verify:

- [ ] All changes are committed and pushed. Ideally but not necessarily merged to `main`.
- [ ] Config filename follows the full anemoi naming convention
- [ ] Submodules are updated and pointing to the right commits. Ideally but not necessarily merged to `main`. If the commits are on a branch different than main, you are responsible that it will not be deleted in the near future.
- [ ] An annotated Git tag has been pushed (`v1.2.0` or `<variant>/v1.2.0`)
- [ ] A GitHub release has been created from the tag, with a description of the dataset.
- [ ] Dataset description includes link to this repo and the tag.