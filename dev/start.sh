#!/usr/bin/env bash

SCRIPT_DIR=$(cd $(dirname "${BASH_SOURCE[0]}") && pwd)
ZELLIJ_CONFIG="-l ${SCRIPT_DIR}/local/layout.kdl"

zellij ${ZELLIJ_CONFIG} || bash <(curl -L zellij.dev/launch) ${ZELLIJ_CONFIG}
