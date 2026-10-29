#!/bin/bash
# Build an anemoi lightning dataset from the preprocessed NetCDF files.
#
# Run preprocessing first:
#   sbatch scripts/preprocess.sh icon   # or inca
#
# Usage:
#   sbatch scripts/build.sh [icon|inca] [output_zarr_path]
#
# Default grid: icon
#
#SBATCH --job-name=build-lightning-dataset
#SBATCH --partition=postproc
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=logs/build-%j.out
#SBATCH --error=logs/build-%j.err

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

GRID="${1:-icon}"

case "$GRID" in
  icon)
    CONFIG="${REPO_DIR}/config/varda-lightning-thx-1km-2005-2025-10min-v1.yaml"
    DEFAULT_OUTPUT="/store_new/mch/msclim/anemoi-datasets/varda-lightning-thx-1km-2005-2025-10min-v1.zarr"
    ;;
  inca)
    CONFIG="${REPO_DIR}/config/varda-lightning-thx-1km-2005-2025-10min-v1-inca.yaml"
    DEFAULT_OUTPUT="/store_new/mch/msclim/anemoi-datasets/varda-lightning-thx-1km-2005-2025-10min-v1-inca.zarr"
    ;;
  *)
    echo "Unknown grid '$GRID'. Use 'icon' or 'inca'." >&2
    exit 1
    ;;
esac

OUTPUT="${2:-$DEFAULT_OUTPUT}"

echo "Grid   : $GRID"
echo "Config : $CONFIG"
echo "Output : $OUTPUT"
echo "Started: $(date -u)"

source "${REPO_DIR}/.venv/bin/activate"

anemoi-datasets create "$CONFIG" "$OUTPUT"

echo "Done   : $(date -u)"
