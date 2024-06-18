#!/usr/bin/env bash

# Script to populate deployment with absolute paths of environment

if [[ "$1" == "-h" || "$1" == "--help" || "$#" -ne 3 ]]; then
    echo "Usage: $0 <deployment-name> <path-to-odin-data-prefix> <path-to-venv>"
    exit 0
fi

DEPLOYMENT=$1
ODIN_DATA=$2
VENV=$3

SCRIPT_DIR=$(cd $(dirname "${BASH_SOURCE[0]}") && pwd)

LOCAL=${SCRIPT_DIR}/local

# Check if local already exists
if [ -d ${LOCAL} ]; then
    echo "Local deployment ${LOCAL} already exists. Please remove it if you want to replace it."
    exit 1
fi

mkdir ${LOCAL}
cp ${SCRIPT_DIR}/${DEPLOYMENT}/* ${LOCAL}

SERVER="${LOCAL}/stOdinServer.sh"
FR="${LOCAL}/stFrameReceiver*.sh"
FR_CONFIG="${LOCAL}/fr*.json"
FP="${LOCAL}/stFrameProcessor*.sh"
FP_CONFIG="${LOCAL}/fp*.json"
META="${LOCAL}/stMetaWriter.sh"
LAYOUT="${LOCAL}/layout.kdl"

sed -i "s+<ODIN_DATA>+${ODIN_DATA}+g" ${FR} ${FR_CONFIG} ${FP} ${FP_CONFIG}
sed -i "s+<VENV>+${VENV}+g" ${SERVER} ${META}
sed -i "s+<SCRIPT_DIR>+${LOCAL}+g" ${LAYOUT}
