#!/bin/bash
# Grid THX lightning strikes onto ICON or INCA/RADAR using the bundled lightning-grid CLI.
# The CLI is provided by src/lightning_anemoi_dataset and installed in the repo venv.
#
# Usage:
#   sbatch scripts/preprocess.sh [icon|inca]
#
# Default grid: icon
#
#SBATCH --job-name=preprocess-lightning
#SBATCH --partition=postproc
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=12:00:00
#SBATCH --output=logs/preprocess-%j.out
#SBATCH --error=logs/preprocess-%j.err

set -euo pipefail

REPO_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

GRID="${1:-icon}"

case "$GRID" in
  icon|inca) ;;
  *) echo "Unknown grid '$GRID'. Use 'icon' or 'inca'." >&2; exit 1 ;;
esac

CONFIG="${REPO_DIR}/config/preprocess/${GRID}.yaml"
echo "Grid   : $GRID"
echo "Config : $CONFIG"
echo "Started: $(date -u)"

source "${REPO_DIR}/.venv/bin/activate"

lightning-grid --config "$CONFIG" --verbose

echo "Done   : $(date -u)"
