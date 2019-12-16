![SC2 Banner](resources/SC2_Banner.png)
https://spectrumcollaborationchallenge.com

## Repository Structure

The following section describes the proposed branch naming convention and initial directory structure for CIL development.

### Branches

* **master:** The master branch always contains the official version of the CIL. All changes to master must occur via a merge request.
* **proposal/foo:** Use branches beginning with "proposal/" to work on draft CIL updates. This can also be used to flesh out a new feature proposal with code. "foo" should be replaced with a short but descriptive name for the feature.
* **feature/foo:** Branches beginning with "feature/" are for working on formal CIL updates. Any merge request for getting code into the master branch will start from a feature branch. "foo" should be replaced with a short but descriptive name for the feature.

### Directories

* **doc:** Documentation source files or utilities related to automatically generating documentation, assuming the CIL development approach uses languages with automatic documentation tools.
* **proto:** If using Protocol Buffers, all .proto files will be found in this directory.
* **examples:** Simple python examples demonstrating a collaboration server and peer interaction.
* **tools:** Analytic and diagnostic utilities useful when developing with the CIL.

## Best Practices

### Git Discipline

DARPA recommends that the CIL Council adopts an approach similar to that described [here](https://spin.atomicobject.com/2017/04/23/maintain-clean-git-history/) regarding how and when to rebase and/or squash branches.

### Style Guides

CIL development will involve a relatively large team from a variety of development backgrounds. To keep the CIL code readable, DARPA recommends that the CIL Council adopts a style guide for each programming language used in CIL development. Here are some proposed style guides for potential CIL development languages:

* **Protocol Buffers:** [Google's Protocol Buffer Style Guide](https://developers.google.com/protocol-buffers/docs/style)
* **Python:** [PEP8](https://www.python.org/dev/peps/pep-0008/)
  * Note: A further recommendation is to use [flake8](http://flake8.pycqa.org/en/latest/) for automatic PEP8 style guide and syntax error checking.
* **Others:** To be updated as necessary