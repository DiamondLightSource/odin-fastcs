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

1. Clone odin-data and open in its devcontainer (for now, checkout fastcs-dev branch)
2. Build odin-data into `vscode_prefix`

    i. `CMake: Delete Cache and Reconfigure` (select a compiler, /usr/bin/gcc is
    probably best)

    ii. `CMake: Install`

3. `Workspaces: Add Folder to Workspace...` to add odin-fastcs to the workspace
4. Install odin-fastcs and its odin dev environment

    i. `pip install -e .[dev,odin]`

    ii. `Python: Select Interpreter` and set it to `/venv/bin/python` for the workspace

5. Prepare the dev environment

    i. `dev/configure.sh one_node_fp /workspaces/odin-data/vscode_prefix /venv`

6. Run the dev environment

    i. `dev/start.sh` (it may print some garbage to the terminal while it installs)

    ii. Click in the right panel and hit enter to run the odin server once all processes
    running

    iii. To close zelijj and the processes, `Ctrl+Q`

7. Run the `Odin IOC` launch config to run the odin-fastcs IOC

If you need to run a dev version of any of the applications, stop that process in the
deployment and run/debug it manually. There is a vscode launch config for an odin server
using the same config as the dev deployment for this purpose.

At boot time, FastCS will generate UIs that can be opened in Phoebus. This is the
clearest way to see the PVs that have been generated for the Odin server. It is also
possible to run `dbl()` in the EPICS shell to print a flat list of PVs.

Odin FastCS does not do much unless it has an Odin control server to talk to. It is
possible to test some functionality in isolation by dumping server responses and creating
tests that parse those responses. Responses can be dumped from various Odin systems and
tests written against them that can run in CI to ensure support for those systems is not
broken (or that the adapters need to be updated). The `tests/dump_server_response.py`
helper script will generate json files for each adapter in an Odin server to write tests
against.

<!-- README only content. Anything below this line won't be included in index.md -->

See https://diamondlightsource.github.io/odin-fastcs for more detailed documentation.
