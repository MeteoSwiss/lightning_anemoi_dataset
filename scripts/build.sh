#!/bin/bash
# Build an anemoi lightning dataset using a config from config/.
#
# Usage:
#   sbatch scripts/build.sh [icon|inca] [radius_km] [output_dir]
#
# Examples:
#   sbatch scripts/build.sh icon 8
#   sbatch scripts/build.sh inca 8
#   sbatch scripts/build.sh icon 8 /tmp
#
# The script looks for config/varda-lightning-thx{R}km-1km-*-10min-v1[-inca].yaml
# and uses it directly. The output zarr name comes from the config's `name:` field.
#
# Default: grid=icon  radius=8
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

# SLURM copies the script to a temp dir, so BASH_SOURCE[0] won't point to the repo.
# SLURM_SUBMIT_DIR is the directory where sbatch was called from (the repo root).
REPO_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

GRID="${1:-icon}"
RADIUS="${2:-8}"

case "$GRID" in
  icon|inca) ;;
  *) echo "Unknown grid '${GRID}'. Use 'icon' or 'inca'." >&2; exit 1 ;;
esac

# Find the dataset config for this grid + radius.
SUFFIX=""
[[ "$GRID" == "inca" ]] && SUFFIX="-inca"
PATTERN="${REPO_DIR}/config/varda-lightning-thx${RADIUS}km-1km-*-10min-v1${SUFFIX}.yaml"

DATASET_CONFIG=""
for f in ${REPO_DIR}/config/varda-lightning-thx${RADIUS}km-1km-*-10min-v1${SUFFIX}.yaml; do
  [[ -f "$f" ]] && DATASET_CONFIG="$f" && break
done
if [[ -z "$DATASET_CONFIG" ]]; then
  echo "No dataset config found matching: $PATTERN" >&2
  echo "Create config/varda-lightning-thx${RADIUS}km-1km-<period>-10min-v1${SUFFIX}.yaml first." >&2
  exit 1
fi

source "${REPO_DIR}/.venv/bin/activate"

DATASET_NAME="$(python3 -c "import yaml; print(yaml.safe_load(open('$DATASET_CONFIG'))['name'])")"
OUTPUT_DIR="${3:-/store_new/mch/msclim/anemoi-datasets}"
OUTPUT="${OUTPUT_DIR}/${DATASET_NAME}.zarr"

echo "Grid    : $GRID"
echo "Radius  : ${RADIUS} km"
echo "Config  : $DATASET_CONFIG"
echo "Dates   : $(python3 -c "import yaml; c=yaml.safe_load(open('$DATASET_CONFIG')); print(c['dates']['start'], '→', c['dates']['end'])")"
echo "Output  : $OUTPUT"
echo "Started : $(date -u)"
echo ""

ulimit -c 0  # suppress core dump — crash is in C extension cleanup after zarr is written
MALLOC_CHECK_=0 anemoi-datasets create "$DATASET_CONFIG" "$OUTPUT"
status=$?
if [[ $status -ne 0 && $status -ne 134 ]]; then  # 134 = SIGABRT from harmless shutdown crash
    echo "anemoi-datasets failed with exit code $status" >&2
    exit $status
fi

python3 -c "import zarr; z=zarr.open('$OUTPUT','r+'); z.attrs.update({'resolution':'1km'})"

echo ""
echo "Done    : $(date -u)"
