#!/bin/bash
# Part B of a circular dependency

echo "Loading cycle_b.sh..."
source ./cycle_a.sh
