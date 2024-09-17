[![CI](https://github.com/DiamondLightSource/fastcs-odin/actions/workflows/ci.yml/badge.svg)](https://github.com/DiamondLightSource/fastcs-odin/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/DiamondLightSource/fastcs-odin/branch/main/graph/badge.svg)](https://codecov.io/gh/DiamondLightSource/fastcs-odin)
[![PyPI](https://img.shields.io/pypi/v/fastcs-odin.svg)](https://pypi.org/project/fastcs-odin)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

# FastCS Odin

FastCS support for the Odin detector software framework

Source          | <https://github.com/DiamondLightSource/fastcs-odin>
:---:           | :---:
PyPI            | `pip install fastcs-odin`
Docker          | `docker run ghcr.io/diamondlightsource/fastcs-odin:latest`
Documentation   | <https://diamondlightsource.github.io/fastcs-odin>
Releases        | <https://github.com/DiamondLightSource/fastcs-odin/releases>

## Development

In most cases it should be sufficient to work within the fastcs-odin devcontainer (or a
virtualenv) and run the unit tests to develop new features and bug fixes.

In order to develop and test fastcs-odin alongside local dev versions of odin-control
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

1. Clone [odin-data] (next to fastcs-odin), checkout the `fastcs-dev` branch and re-open
   in devcontainer
2. Add fastcs-odin to the workspace `> Workspaces: Add Folder to Workspace...`

    i. If it asks to reload window, then do so

3. Install the recommended extensions with `> Extensions: Show Recommended Extensions`
4. Build odin-data into `/odin`

    i. `> CMake: Delete Cache and Reconfigure` and select a compiler, e.g.
    `/usr/bin/gcc`

    ii. `> CMake: Install`

5. Install fastcs-odin and its odin dev environment

    i. `> Python: Select Interpreter`, `Select at workspace level` and select
    `/venv/bin/python`

    ii. Run `$ pip install -e .[dev,odin]` at the root of fastcs-odin

6. Prepare the dev environment (in the root of fastcs-odin)

    i. `$ dev/configure.sh one_node_fp /workspaces/odin-data/vscode_prefix /venv`

    ii. `$ zellij`, wait for it to finish installing and close with `Ctrl+Q`

7. Run the dev environment (in the root of fastcs-odin)

    i. `$ dev/start.sh`

8. `> Debug: Select and Start Debugging` and select `Odin IOC` to run the IOC

UIs will be generated in the root of fastcs-odin that can be opened in Phoebus. This is
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

While it is necessary to work on odin-control / odin-data alongside fastcs-odin in some
cases, once these additions have been made they should be backed by tests that can be
run without the full development environment. This means in most case it is possible to
develop fastcs-odin in isolation and trust the unit tests to give a good indication
that things are working as expected, and so that the same checks can be made in CI and
reduce manual testing during code review.

It is possible to test some functionality in isolation by dumping server responses and
creating tests that parse those responses. Responses can be dumped from various Odin
systems and tests written against them that can run in CI to ensure support for those
systems is not broken (or get early warning that an adapter needs to be updated to work
with the latest fastcs-odin). The `tests/dump_server_response.py` helper script will
generate json files for each adapter in an Odin server to write tests against.

[odin-data]: https://github.com/odin-detector/odin-data
[odin-data-developer]: https://github.com/odin-detector/odin-data/pkgs/container/odin-data-developer

<!-- README only content. Anything below this line won't be included in index.md -->

See https://diamondlightsource.github.io/fastcs-odin for more detailed documentation.
