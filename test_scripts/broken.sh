#!/bin/bash
# Script with missing source files

source ./lib/utils.sh

# This file does not exist
source ./nonexistent_module.sh

# Neither does this one
. ./missing_helpers.sh

log_info "Running with broken dependencies..."
