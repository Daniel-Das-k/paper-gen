#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "$script_dir/.." && pwd)"
demo_dir="$repo_dir/demo_data"
output_dir="$repo_dir/outputs"

read -r -p "Delete the local demo database, uploads, and demo PDF exports? [y/N] " reply
if [[ "$reply" != "y" && "$reply" != "Y" ]]; then
  echo "Reset cancelled."
  exit 0
fi

if [[ "$demo_dir" != "$repo_dir/demo_data" ]]; then
  echo "Refusing to reset an unexpected path."
  exit 1
fi

if [[ -d "$demo_dir" ]]; then
  rm -rf "$demo_dir"
fi
if [[ -d "$output_dir" ]]; then
  find "$output_dir" -maxdepth 1 -type f -name 'demo-*.pdf' -delete
fi

echo "Local demo data was removed. It cannot be recovered."

