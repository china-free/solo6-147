#!/bin/bash
# Part A of a circular dependency

echo "Loading cycle_a.sh..."
source ./cycle_b.sh
