#!/bin/bash
# Main entry point - sources multiple modules

source ./lib/utils.sh
source ./lib/config.sh

echo "Starting deployment..."
./deploy.sh
