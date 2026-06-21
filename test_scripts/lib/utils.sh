#!/bin/bash
# Utility functions

function log_info() {
    echo "[INFO] $1"
}

function log_error() {
    echo "[ERROR] $1" >&2
}
