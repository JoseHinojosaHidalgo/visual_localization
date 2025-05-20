import os
import csv
import math
import argparse
import pandas as pd
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
from collections import defaultdict
from svl.tms import FlightZoneDownloader, FlightZone, TileDownloader

def tile_xyz_to_bounds(x, y, z):
    """Convert tile coordinates to bounds (top-left and bottom-right)"""
    n = 2 ** z

    lon_left = x / n * 360.0 - 180.0
    lon_right = (x + 1) / n * 360.0 - 180.0

    lat_top_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_bottom_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))

    lat_top = math.degrees(lat_top_rad)
    lat_bottom = math.degrees(lat_bottom_rad)

    return lat_top, lon_left, lat_bottom, lon_right

def download_satellite_tiles(top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon, 
                           api_key, output_path="./data/output/sat", zoom_level=20):
    """
    Download satellite tiles for the specified geographic area.
    
    Args:
        top_left_lat (float): Top left latitude
        top_left_lon (float): Top left longitude
        bottom_right_lat (float): Bottom right latitude
        bottom_right_lon (float): Bottom right longitude
        api_key (str): MapTiler API key
        output_path (str): Output directory path
        zoom_level (int): Zoom level for tile download
    
    Returns:
        str: Path to the CSV file containing tile coordinates
    """
    # Define the flight zone
    flight_zone = FlightZone(
        top_left_lat=top_left_lat,
        top_left_long=top_left_lon,
        bottom_right_lat=bottom_right_lat,
        bottom_right_long=bottom_right_lon,
    )

    # Define the tile downloader
    tms_url = f"https://api.maptiler.com/tiles/satellite/{{z}}/{{x}}/{{y}}.jpg?key={api_key}"
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

    # Create output directory
    os.makedirs(output_path, exist_ok=True)

    # Download tiles and save mosaic
    print(f"Downloading tiles for area: ({top_left_lat}, {top_left_lon}) to ({bottom_right_lat}, {bottom_right_lon})")
    flight_zone_downloader.download_tiles_and_save_as_mosaic(
        zoom_level=zoom_level,
        output_path=output_path,
        mosaic_format="tiff",
    )

    # Create CSV file with tile coordinates
    csv_path = os.path.join(output_path, "map.csv")
    with open(csv_path, mode="w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Filename", "Top_left_lat", "Top_left_lon", "Bottom_right_lat", "Bottom_right_lon"])

        # Iterate through files in the tiles directory
        tiles_dir = os.path.join(output_path, "tiles")
        if os.path.exists(tiles_dir):
            for filename in os.listdir(tiles_dir):
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

    print(f"Created coordinate CSV: {csv_path}")
    return csv_path

def create_stitched_csv(csv_path, output_csv_path, block_size=4):
    """
    Creates a new CSV file with coordinates for the stitched images.
    
    Args:
        csv_path (str): Path to original CSV file with 256x256 image coordinates.
        output_csv_path (str): Path to save the new CSV file for stitched images.
        block_size (int): Number of images per side in each stitched block.
    
    Returns:
        pd.DataFrame: DataFrame containing the stitched image coordinates.
    """
    # Read the original coordinates
    df = pd.read_csv(csv_path)
    
    # Identify unique latitude and longitude values
    unique_top_lats = sorted(df['Top_left_lat'].unique(), reverse=True)  # Higher is north
    unique_top_lons = sorted(df['Top_left_lon'].unique())  # Lower is west
    
    # Calculate how many blocks we need
    num_blocks_lat = (len(unique_top_lats) + block_size - 1) // block_size
    num_blocks_lon = (len(unique_top_lons) + block_size - 1) // block_size
    
    # Create empty lists to store the new data
    filenames = []
    top_left_lats = []
    top_left_lons = []
    bottom_right_lats = []
    bottom_right_lons = []
    
    # Process each regular block
    for lat_block in range(num_blocks_lat):
        for lon_block in range(num_blocks_lon):
            # Get the latitude and longitude ranges for this block
            lat_start_idx = lat_block * block_size
            lon_start_idx = lon_block * block_size
            
            # Handle edge cases when we reach the end of our coordinates
            lat_end_idx = min(lat_start_idx + block_size, len(unique_top_lats))
            lon_end_idx = min(lon_start_idx + block_size, len(unique_top_lons))
            
            if lat_start_idx >= len(unique_top_lats) or lon_start_idx >= len(unique_top_lons):
                continue  # Skip if we're out of range
                
            # Get the coordinates for this block
            if lat_end_idx > 0 and lon_end_idx > 0:
                top_left_lat = unique_top_lats[lat_start_idx]
                top_left_lon = unique_top_lons[lon_start_idx]
                
                # For bottom right, we need coordinates from the original tiles
                # Find the bottom-right coordinates of the bottom-right tile in this block
                bottom_right_matches = df[
                    (df['Top_left_lat'] == unique_top_lats[lat_end_idx-1]) & 
                    (df['Top_left_lon'] == unique_top_lons[lon_end_idx-1])
                ]
                
                if not bottom_right_matches.empty:
                    bottom_right_lat = bottom_right_matches['Bottom_right_lat'].iloc[0]
                    bottom_right_lon = bottom_right_matches['Bottom_right_lon'].iloc[0]
                    
                    # Add to our lists
                    filenames.append(f"stitched_block_{lat_block}_{lon_block}.png")
                    top_left_lats.append(top_left_lat)
                    top_left_lons.append(top_left_lon)
                    bottom_right_lats.append(bottom_right_lat)
                    bottom_right_lons.append(bottom_right_lon)
    
    # Add entries for additional images (for unused original images)
    # Get all original filenames
    all_images = set(df['Filename'])
    
    # Determine which images would be used in the standard grid
    used_images = set()
    for lat_block in range(num_blocks_lat):
        for lon_block in range(num_blocks_lon):
            lat_start_idx = lat_block * block_size
            lon_start_idx = lon_block * block_size
            
            block_lats = unique_top_lats[lat_start_idx:min(lat_start_idx + block_size, len(unique_top_lats))]
            block_lons = unique_top_lons[lon_start_idx:min(lon_start_idx + block_size, len(unique_top_lons))]
            
            for lat in block_lats:
                for lon in block_lons:
                    matching_rows = df[(df['Top_left_lat'] == lat) & (df['Top_left_lon'] == lon)]
                    if not matching_rows.empty:
                        used_images.add(matching_rows['Filename'].iloc[0])
    
    # Find unused images
    unused_images = all_images - used_images
    if unused_images:
        unused_df = df[df['Filename'].isin(unused_images)]
        
        # Group them into additional blocks
        for i in range(0, len(unused_df), block_size * block_size):
            chunk = unused_df.iloc[i:min(i + block_size * block_size, len(unused_df))]
            
            if not chunk.empty:
                # Calculate the bounding box for this additional stitched image
                additional_top_left_lat = chunk['Top_left_lat'].max()
                additional_top_left_lon = chunk['Top_left_lon'].min()
                additional_bottom_right_lat = chunk['Bottom_right_lat'].min()
                additional_bottom_right_lon = chunk['Bottom_right_lon'].max()
                
                # Add to our lists
                filenames.append(f"stitched_additional_{i // (block_size * block_size)}.png")
                top_left_lats.append(additional_top_left_lat)
                top_left_lons.append(additional_top_left_lon)
                bottom_right_lats.append(additional_bottom_right_lat)
                bottom_right_lons.append(additional_bottom_right_lon)
    
    # Create the new dataframe
    stitched_df = pd.DataFrame({
        'Filename': filenames,
        'Top_left_lat': top_left_lats,
        'Top_left_lon': top_left_lons,
        'Bottom_right_lat': bottom_right_lats,
        'Bottom_right_lon': bottom_right_lons
    })
    
    # Save to CSV
    stitched_df.to_csv(output_csv_path, index=False)
    print(f"Created stitched coordinates CSV: {output_csv_path}")
    
    return stitched_df

def stitch_satellite_images(csv_path, images_dir, output_dir, block_size=4):
    """
    Stitches 256x256 satellite images into larger images.
    Uses all available images and fills missing spots with white.
    
    Args:
        csv_path (str): Path to CSV file containing image coordinates.
        images_dir (str): Directory containing the 256x256 satellite images.
        output_dir (str): Directory to save the stitched images.
        block_size (int): Number of images per side in the stitched block
    
    Returns:
        list: List of paths to the created stitched images.
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Read coordinates from CSV
    df = pd.read_csv(csv_path)
    
    # First, identify unique latitude and longitude values
    unique_top_lats = sorted(df['Top_left_lat'].unique(), reverse=True)  # Higher is north
    unique_top_lons = sorted(df['Top_left_lon'].unique())  # Lower is west
    
    # Calculate how many blocks we need (ceil division to include all images)
    num_blocks_lat = (len(unique_top_lats) + block_size - 1) // block_size
    num_blocks_lon = (len(unique_top_lons) + block_size - 1) // block_size
    
    created_images = []
    
    # Create a white fill image for missing spots
    white_image = Image.new('RGB', (256, 256), (255, 255, 255))
    
    # Process each block
    for lat_block in range(num_blocks_lat):
        for lon_block in range(num_blocks_lon):
            # Get the latitude and longitude ranges for this block
            lat_start_idx = lat_block * block_size
            lon_start_idx = lon_block * block_size
            
            # Get coordinates for this block, handling potential out-of-range indices
            block_lats = unique_top_lats[lat_start_idx:min(lat_start_idx + block_size, len(unique_top_lats))]
            block_lons = unique_top_lons[lon_start_idx:min(lon_start_idx + block_size, len(unique_top_lons))]
            
            # Create a new blank image for the stitched result
            stitched_image = Image.new('RGB', (256 * block_size, 256 * block_size), (255, 255, 255))
            
            # Flag to track if at least one image was placed in this block
            has_any_images = False
            
            # For each position in the block
            for i, lat in enumerate(block_lats):
                for j, lon in enumerate(block_lons):
                    # Find the image that starts at this coordinate
                    matching_rows = df[(df['Top_left_lat'] == lat) & (df['Top_left_lon'] == lon)]
                    
                    if len(matching_rows) == 0:
                        print(f"No image found for coordinates {lat}, {lon}, filling with white")
                        continue
                    
                    # Get the first matching file
                    filename = matching_rows['Filename'].iloc[0]
                    img_path = os.path.join(images_dir, filename)
                    
                    if not os.path.exists(img_path):
                        print(f"Warning: Image file not found: {img_path}, filling with white")
                        continue
                    
                    try:
                        # Open the image and paste it into the right position in the stitched image
                        img = Image.open(img_path)
                        stitched_image.paste(img, (j * 256, i * 256))
                        has_any_images = True
                    except Exception as e:
                        print(f"Error processing {img_path}: {e}, filling with white")
            
            # Save the stitched image if at least one component image was found
            if has_any_images:
                output_filename = f"stitched_block_{lat_block}_{lon_block}.png"
                output_path = os.path.join(output_dir, output_filename)
                stitched_image.save(output_path)
                created_images.append(output_path)
                print(f"Created stitched image: {output_path}")
    
    return created_images

def stitch_all_images(csv_path, images_dir, output_dir, block_size=4):
    """
    Ensures all images in the CSV are included in at least one stitched image.
    
    Args:
        csv_path (str): Path to CSV file containing image coordinates.
        images_dir (str): Directory containing the satellite images.
        output_dir (str): Directory to save the stitched images.
        block_size (int): Number of images per side in the stitched block.
    
    Returns:
        list: List of paths to the created stitched images.
    """
    # First run the standard stitching function
    created_images = stitch_satellite_images(csv_path, images_dir, output_dir, block_size)
    
    # Now check if any images were left out
    df = pd.read_csv(csv_path)
    used_images = set()
    
    # Get unique latitude and longitude values
    unique_top_lats = sorted(df['Top_left_lat'].unique(), reverse=True)
    unique_top_lons = sorted(df['Top_left_lon'].unique())
    
    # Calculate how many blocks we created
    num_blocks_lat = (len(unique_top_lats) + block_size - 1) // block_size
    num_blocks_lon = (len(unique_top_lons) + block_size - 1) // block_size
    
    # For each block, mark which images should have been used
    for lat_block in range(num_blocks_lat):
        for lon_block in range(num_blocks_lon):
            lat_start_idx = lat_block * block_size
            lon_start_idx = lon_block * block_size
            
            block_lats = unique_top_lats[lat_start_idx:min(lat_start_idx + block_size, len(unique_top_lats))]
            block_lons = unique_top_lons[lon_start_idx:min(lon_start_idx + block_size, len(unique_top_lons))]
            
            for lat in block_lats:
                for lon in block_lons:
                    matching_rows = df[(df['Top_left_lat'] == lat) & (df['Top_left_lon'] == lon)]
                    if not matching_rows.empty:
                        used_images.add(matching_rows['Filename'].iloc[0])
    
    # Check if all images were used
    all_images = set(df['Filename'])
    unused_images = all_images - used_images
    
    if unused_images:
        print(f"Found {len(unused_images)} unused images. Creating additional stitched images to include them.")
        
        # Create one or more additional stitched images for the unused files
        unused_df = df[df['Filename'].isin(unused_images)]
        
        # Process in blocks of block_size²
        for i in range(0, len(unused_df), block_size * block_size):
            chunk = unused_df.iloc[i:i + block_size * block_size]
            
            # Create a new blank image
            stitched_image = Image.new('RGB', (256 * block_size, 256 * block_size), (255, 255, 255))
            
            # Place each image in the stitched result
            for idx, (_, row) in enumerate(chunk.iterrows()):
                row_idx = idx // block_size
                col_idx = idx % block_size
                
                filename = row['Filename']
                img_path = os.path.join(images_dir, filename)
                
                if os.path.exists(img_path):
                    try:
                        img = Image.open(img_path)
                        stitched_image.paste(img, (col_idx * 256, row_idx * 256))
                    except Exception as e:
                        print(f"Error processing {img_path}: {e}")
            
            # Save the additional stitched image
            output_filename = f"stitched_additional_{i // (block_size * block_size)}.png"
            output_path = os.path.join(output_dir, output_filename)
            stitched_image.save(output_path)
            created_images.append(output_path)
            print(f"Created additional stitched image: {output_path}")
    
    return created_images

def download_and_stitch_satellite_images(top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon, 
                                        stitch_size=4, api_key=None, output_path="./data/output", zoom_level=20, skip_download=False):
    """
    Complete pipeline: Download satellite tiles and stitch them together.
    
    Args:
        top_left_lat (float): Top left latitude
        top_left_lon (float): Top left longitude  
        bottom_right_lat (float): Bottom right latitude
        bottom_right_lon (float): Bottom right longitude
        stitch_size (int): Number of images per side in each stitched block (e.g., 4 for 4x4 = 16 images per stitched image)
        api_key (str): MapTiler API key (if None, will try to get from environment variable MAPTILER_API_KEY)
        output_path (str): Base output directory
        zoom_level (int): Zoom level for tile download
    
    Returns:
        tuple: (list of stitched image paths, path to stitched CSV file)
    """
    
    # Get API key from environment if not provided
    if api_key is None:
        api_key = os.getenv('MAPTILER_API_KEY')
        if api_key is None:
            raise ValueError("API key must be provided either as parameter or MAPTILER_API_KEY environment variable")
    
    # Set up paths
    sat_output_path = os.path.join(output_path, "sat")
    stitched_output_path = os.path.join(output_path, "stitched")
    
    csv_path = os.path.join(sat_output_path, "map.csv")
    if not skip_download:
        print("Step 1: Downloading satellite tiles...")
        # Download tiles
        csv_path = download_satellite_tiles(
            top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon,
            api_key, sat_output_path, zoom_level
        )
    
    print("\nStep 2: Stitching images...")
    # Stitch images
    images_dir = os.path.join(sat_output_path, "tiles")
    stitched_images = stitch_all_images(csv_path, images_dir, stitched_output_path, stitch_size)
    
    print("\nStep 3: Creating stitched image coordinates CSV...")
    # Create CSV for stitched images
    stitched_csv_path = os.path.join(stitched_output_path, "map.csv")
    stitched_df = create_stitched_csv(csv_path, stitched_csv_path, stitch_size)
    
    print(f"\nCompleted! Created {len(stitched_images)} stitched images.")
    print(f"Stitched images saved to: {stitched_output_path}")
    print(f"Stitched image coordinates saved to: {stitched_csv_path}")
    
    return stitched_images, stitched_csv_path

# Main function with command line argument parsing
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Download and stitch satellite images from MapTiler')
    
    # Required coordinate arguments
    parser.add_argument('--top-left-lat', type=float, required=True,
                       help='Top left latitude coordinate')
    parser.add_argument('--top-left-lon', type=float, required=True,
                       help='Top left longitude coordinate')
    parser.add_argument('--bottom-right-lat', type=float, required=True,
                       help='Bottom right latitude coordinate')
    parser.add_argument('--bottom-right-lon', type=float, required=True,
                       help='Bottom right longitude coordinate')
    
    # Optional arguments
    parser.add_argument('--stitch-size', type=int, default=4,
                       help='Number of images per side in stitched block (default: 4 for 4x4 grid)')
    parser.add_argument('--output-path', type=str, default='./data/output',
                       help='Output directory path (default: ./data/output)')
    parser.add_argument('--zoom-level', type=int, default=20,
                       help='Zoom level for satellite tiles (default: 20)')
    parser.add_argument('--skip-download', action=argparse.BooleanOptionalAction,
                       help='Skips tile download')
    
    args = parser.parse_args()
    
    # Get API key from environment variable
    api_key = os.getenv('MAPTILER_API_KEY')
    if api_key is None:
        print("Error: MAPTILER_API_KEY environment variable is not set.")
        print("Please set it with: export MAPTILER_API_KEY='your_api_key_here'")
        exit(1)
    
    try:
        print(f"Starting download and stitching process...")
        print(f"Area: ({args.top_left_lat}, {args.top_left_lon}) to ({args.bottom_right_lat}, {args.bottom_right_lon})")
        print(f"Stitch size: {args.stitch_size}x{args.stitch_size}")
        print(f"Output path: {args.output_path}")
        print(f"Zoom level: {args.zoom_level}")
        
        stitched_images, csv_path = download_and_stitch_satellite_images(
            top_left_lat=args.top_left_lat,
            top_left_lon=args.top_left_lon,
            bottom_right_lat=args.bottom_right_lat,
            bottom_right_lon=args.bottom_right_lon,
            stitch_size=args.stitch_size,
            api_key=api_key,
            output_path=args.output_path,
            zoom_level=args.zoom_level,
            skip_download=args.skip_download
        )
        
        print(f"\nSuccess! Created {len(stitched_images)} stitched satellite images.")
        
    except Exception as e:
        print(f"An error occurred: {e}")
        exit(1)