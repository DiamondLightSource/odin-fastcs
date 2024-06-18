[![CI](https://github.com/DiamondLightSource/odin-fastcs/actions/workflows/ci.yml/badge.svg)](https://github.com/DiamondLightSource/odin-fastcs/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/DiamondLightSource/odin-fastcs/branch/main/graph/badge.svg)](https://codecov.io/gh/DiamondLightSource/odin-fastcs)
[![PyPI](https://img.shields.io/pypi/v/odin-fastcs.svg)](https://pypi.org/project/odin-fastcs)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

# Odin FastCS
FastCS support for the Odin detector software framework

Source          | <https://github.com/DiamondLightSource/odin-fastcs>
:---:           | :---:
PyPI            | `pip install odin-fastcs`
Docker          | `docker run ghcr.io/diamondlightsource/odin-fastcs:latest`
Documentation   | <https://diamondlightsource.github.io/odin-fastcs>
Releases        | <https://github.com/DiamondLightSource/odin-fastcs/releases>

## Development

In most cases it should be sufficient to work within the odin-fastcs devcontainer (or a
virtualenv) and run the unit tests to develop new features and bug fixes.

In order to develop and test odin-fastcs alongside local dev versions of odin-control
and odin-data applications, a development environment can be run up from the odin-data
devcontainer.

### Full Development Environment

The following instructions assume use of vscode, as it makes it very convenient to set up
an environment that "just works". However, it is possible to run the same environment up
manually using the [odin-data-developer] container and the following steps should still
provide a good overview.

Note, commands starting with `>` are vscode commands and can be run with `Ctrl+Shift+P`,
while commands starting with `$` are bash commands to be run in a terminal (inside the
vscode devcontainer).

1. Clone [odin-data] (next to odin-fastcs), checkout the `fastcs-dev` branch and re-open
   in devcontainer
2. Add odin-fastcs to the workspace `> Workspaces: Add Folder to Workspace...`

    i. If it asks to reload window, then do so

3. Install the recommended extensions with `> Extensions: Show Recommended Extensions`
4. Build odin-data into `/odin`

    i. `> CMake: Delete Cache and Reconfigure` and select a compiler, e.g.
    `/usr/bin/gcc`

    ii. `> CMake: Install`

5. Install odin-fastcs and its odin dev environment

    i. `> Python: Select Interpreter`, `Select at workspace level` and select
    `/venv/bin/python`

    ii. Run `$ pip install -e .[dev,odin]` at the root of odin-fastcs

6. Prepare the dev environment (in the root of odin-fastcs)

    i. `$ dev/configure.sh one_node_fp /workspaces/odin-data/vscode_prefix /venv`

    ii. `$ zellij`, wait for it to finish installing and close with `Ctrl+Q`

7. Run the dev environment (in the root of odin-fastcs)

    i. `$ dev/start.sh`

8. `> Debug: Select and Start Debugging` and select `Odin IOC` to run the IOC

UIs will be generated in the root of odin-fastcs that can be opened in Phoebus. This is
the clearest way to see the PVs that have been generated for the Odin server. It is also
possible to run `dbl()` in the EPICS shell to print a flat list of PVs.

To run a dev version of any of the applications, stop that process in the deployment (by
clicking the pane and pressing `Ctrl+C`) then run/debug it manually. There is a vscode
launch config for an odin server using the same config as the dev deployment for this
purpose.

To run local versions of odin-data / odin-control python applications install it into
the virtual environment with `$ pip install -e ...` to override the versions installed
from GitHub.

### Isolated Development Environment

While it is necessary to work on odin-control / odin-data alongside odin-fastcs in some
cases, once these additions have been made they should be backed by tests that can be
run without the full development environment. This means in most case it is possible to
develop odin-fastcs in isolation and trust the unit tests to give a good indication
that things are working as expected, and so that the same checks can be made in CI and
reduce manual testing during code review.

It is possible to test some functionality in isolation by dumping server responses and
creating tests that parse those responses. Responses can be dumped from various Odin
systems and tests written against them that can run in CI to ensure support for those
systems is not broken (or get early warning that an adapter needs to be updated to work
with the latest odin-fastcs). The `tests/dump_server_response.py` helper script will
generate json files for each adapter in an Odin server to write tests against.

[odin-data]: https://github.com/odin-detector/odin-data
[odin-data-developer]: https://github.com/odin-detector/odin-data/pkgs/container/odin-data-developer

<!-- README only content. Anything below this line won't be included in index.md -->

See https://diamondlightsource.github.io/odin-fastcs for more detailed documentation.
