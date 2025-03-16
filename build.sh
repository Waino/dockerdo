#!/bin/bash

set -eux

# Update the bash completion
_DOCKERDO_COMPLETE=bash_source dockerdo > dockerdo/dockerdo.bash-completion

# Build the package
flit build
