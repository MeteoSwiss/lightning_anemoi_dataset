#!/bin/bash
# Build an anemoi lightning dataset from the preprocessed NetCDF files.
# Dates and paths are read from the corresponding preprocess config.
#
# Usage:
#   sbatch scripts/build.sh [icon|inca] [radius_km] [output_zarr_path]
#
# Examples:
#   sbatch scripts/build.sh icon 8
#   sbatch scripts/build.sh inca 16
#   sbatch scripts/build.sh icon 4 /tmp/test.zarr
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

GRID="${1:-icon}"
RADIUS="${2:-8}"

case "$GRID" in
  icon|inca) ;;
  *) echo "Unknown grid '${GRID}'. Use 'icon' or 'inca'." >&2; exit 1 ;;
esac

PREPROCESS_CONFIG="${REPO_DIR}/config/preprocess/${GRID}.yaml"
if [[ ! -f "$PREPROCESS_CONFIG" ]]; then
  echo "Preprocess config not found: $PREPROCESS_CONFIG" >&2
  exit 1
fi

source "${REPO_DIR}/.venv/bin/activate"

# Generate a dataset config from the preprocess config + radius argument.
DATASET_CONFIG="$(mktemp /tmp/anemoi-lightning-XXXXXX.yaml)"
trap 'rm -f "$DATASET_CONFIG"' EXIT

python3 - "$PREPROCESS_CONFIG" "$GRID" "$RADIUS" > "$DATASET_CONFIG" << 'PYEOF'
import sys, yaml
from datetime import datetime, timedelta

preprocess_yaml, grid, radius_str = sys.argv[1], sys.argv[2], sys.argv[3]
radius = float(radius_str)

with open(preprocess_yaml) as f:
    pre = yaml.safe_load(f)

def parse_date(val):
    s = str(val).replace("-", "")
    return datetime.strptime(s, "%Y%m%d")

start_dt = parse_date(pre["start"])
# config.py adds +1 day to stop (end_of_day=True), so stop is the LAST day processed
stop_dt  = parse_date(pre["stop"])
end_dt   = stop_dt.replace(hour=23, minute=50)  # last 10-min step of the last day

start_anemoi = start_dt.strftime("%Y-%m-%dT00:10")
end_anemoi   = end_dt.strftime("%Y-%m-%dT%H:%M")

start_year = start_dt.year
end_year   = stop_dt.year
period     = f"{start_year}-{end_year}" if start_year != end_year else str(start_year)

suffix     = f"-inca-r{int(radius)}" if grid == "inca" else f"-r{int(radius)}"
name       = f"varda-lightning-thx-1km-{period}-10min-v1{suffix}"

data_dir   = pre.get("output_dir", "/store_new/mch/msclim/lightning_gridded")
icon_line  = ""
if grid == "icon":
    icon_grid = pre.get("icon_grid_file",
                        "/store_new/mch/msclim/pronos/icon_grid_0001_R19B08_mch.nc")
    icon_line = f"        icon_grid_path: {icon_grid}"

print(f"""\
name: {name}

description: |
  THX lightning strike counts on the {'ICON-CH1 native' if grid == 'icon' else 'INCA/RADAR LV95'} grid
  at 10-minute temporal resolution, accumulation radius = {int(radius)} km.
  Source: MeteoSwiss THX archive ({data_dir})

licence: CC BY 4.0
attribution: MeteoSwiss
resolution: 1km

dates:
  start: {start_anemoi}
  end:   {end_anemoi}
  frequency: 10m

build:
  group_by: daily

input:
  join:

    - thx-lightning:
        data_dir: {data_dir}
        grid_type: {grid}
        radius_km: {radius}
{icon_line}

    - forcings:
        template: ${{input.join.0.thx-lightning}}
        param:
          - cos_latitude
          - cos_longitude
          - sin_latitude
          - sin_longitude
          - cos_julian_day
          - sin_julian_day
          - cos_local_time
          - sin_local_time
          - insolation
""")
PYEOF

# Derive output path from the dataset name in the generated config
DATASET_NAME="$(python3 -c "import yaml; print(yaml.safe_load(open('$DATASET_CONFIG'))['name'])")"
OUTPUT_DIR="/store_new/mch/msclim/anemoi-datasets"
OUTPUT="${3:-${OUTPUT_DIR}/${DATASET_NAME}.zarr}"

echo "Grid    : $GRID"
echo "Radius  : ${RADIUS} km"
echo "Config  : $PREPROCESS_CONFIG"
echo "Dates   : $(python3 -c "import yaml; c=yaml.safe_load(open('$DATASET_CONFIG')); print(c['dates']['start'], '→', c['dates']['end'])")"
echo "Output  : $OUTPUT"
echo "Started : $(date -u)"
echo ""

MALLOC_CHECK_=0 anemoi-datasets create "$DATASET_CONFIG" "$OUTPUT"

# Set resolution metadata — XarrayFieldList.resolution() is not yet implemented
# upstream, so the zarr attribute stays None without this patch.
python3 -c "import zarr; z=zarr.open('$OUTPUT','r+'); z.attrs.update({'resolution':'1km'})"
echo "Resolution patched: 1km"

echo ""
echo "Done    : $(date -u)"
