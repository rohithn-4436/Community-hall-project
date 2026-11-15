#!/bin/bash

cd "$(dirname "$0")" || exit 1

if [ "$#" -eq 0 ]; then
    echo 'Usage: ./save.sh "commit message"'
    exit 1
fi
echo "Starting community hall project backup"
git add . || exit 1

git commit -m "$*" || exit 1

git push || exit 1

echo "Project successfully pushed to GitHub!"
