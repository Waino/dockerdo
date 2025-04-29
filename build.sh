#!/bin/bash

set -eux

# Update the bash completion
_DOCKERDO_COMPLETE=bash_source dockerdo > dockerdo/dockerdo.bash-completion

# Remove old build artefacts, to force rebuild
rm dist/*.whl dist/*.tar.gz

# Build the package
flit build
