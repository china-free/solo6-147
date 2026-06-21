#!/bin/bash
# Script with dynamic source (variable-based)

MODULE_NAME="config"
MODULE_PATH="./lib/${MODULE_NAME}.sh"

# Dynamic source - cannot be statically resolved
source "$MODULE_PATH"

# Another dynamic pattern
for mod in utils config; do
    source "./lib/${mod}.sh"
done

echo "Dynamic loading complete"
