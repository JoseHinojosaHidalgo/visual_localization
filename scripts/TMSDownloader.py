import os
import csv
import math
from svl.tms import FlightZoneDownloader, FlightZone, TileDownloader

# Define tile to lat/lon conversion
def tile_xyz_to_bounds(x, y, z):
    # Convert tile coordinates to bounds (top-left and bottom-right)
    n = 2 ** z

    lon_left = x / n * 360.0 - 180.0
    lon_right = (x + 1) / n * 360.0 - 180.0

    lat_top_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_bottom_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))

    lat_top = math.degrees(lat_top_rad)
    lat_bottom = math.degrees(lat_bottom_rad)

    return lat_top, lon_left, lat_bottom, lon_right

# Define the flight zone
flight_zone = FlightZone(
    top_left_lat=46.843592,
    top_left_long=-91.994737,
    bottom_right_lat=46.842215,
    bottom_right_long=-91.991058,
)

# Define the tile downloader
tms_url = "https://api.maptiler.com/tiles/satellite/{z}/{x}/{y}.jpg?key=UTSYUKKHsCFi5yHQVC49"
tile_downloader = TileDownloader(
    url=tms_url,
    channels=3,
    api_key=None,
    headers=None,
    img_format="png",
)

# Define the flight zone downloader
flight_zone_downloader = FlightZoneDownloader(
    tile_downloader=tile_downloader,
    flight_zone=flight_zone,
)

# Set output path
output_path = "./data/output/sat"
os.makedirs(output_path, exist_ok=True)

# Download tiles and save mosaic (this creates the .png tiles too)
zoom_level = 20
flight_zone_downloader.download_tiles_and_save_as_mosaic(
    zoom_level=zoom_level,
    output_path=output_path,
    mosaic_format="tiff",
)

# Prepare CSV file
csv_path = os.path.join(output_path, "map.csv")
with open(csv_path, mode="w", newline="") as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["Filename", "Top_left_lat", "Top_left_lon", "Bottom_right_lat", "Bottom_right_lon"])

    # Iterate through files in the directory
    for filename in os.listdir(output_path + "/tiles"):
        if filename.endswith(".png") and "_" in filename:
            try:
                x_str, y_str, z_str = filename.replace(".png", "").split("_")
                x, y, z = int(x_str), int(y_str), int(z_str)
                top_lat, left_lon, bottom_lat, right_lon = tile_xyz_to_bounds(x, y, z)

                writer.writerow([
                    filename,
                    round(top_lat, 6),
                    round(left_lon, 6),
                    round(bottom_lat, 6),
                    round(right_lon, 6),
                ])
            except ValueError:
                continue  # Skip files that don't match the pattern
