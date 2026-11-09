import sys
import zarr

path = sys.argv[1] if len(sys.argv) > 1 else "/store_new/mch/msclim/anemoi-datasets/varda-lightning-thx8km-1km-2025-10min-v1-inca.zarr"
z = zarr.open(path, "r+")
z.attrs.update({"resolution": "1km"})
print(f"Patched resolution=1km in {path}")
