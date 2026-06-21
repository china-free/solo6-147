#!/bin/bash
# Self-referencing script - sources itself

echo "This script sources itself!"
source ./self_ref.sh

echo "This should cause infinite recursion at runtime"
