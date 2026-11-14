#!/bin/bash

# Move to the project directory
cd "$(dirname "$0")"

# Check whether a commit message was provided
if [ "$#" -eq 0 ]; then
    echo "Usage: ./save.sh \"Your commit message\""
    exit 1
fi

# Add, commit and push
git add .
git commit -m "$*"
git push
