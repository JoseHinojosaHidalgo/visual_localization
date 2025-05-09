import os
import pandas as pd
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
from collections import defaultdict

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
    Stitches 256x256 satellite images into larger 1024x1024 images (4x4 blocks).
    Uses all available images and fills missing spots with white.
    
    Args:
        csv_path (str): Path to CSV file containing image coordinates.
        images_dir (str): Directory containing the 256x256 satellite images.
        output_dir (str): Directory to save the stitched images.
        block_size (int): Number of images per side in the stitched block (default 4 for 4x4 grid)
    
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

def visualize_grid_coverage(csv_path):
    """
    Visualizes the coverage of satellite images in a grid.
    Helps to understand how images are arranged.
    
    Args:
        csv_path (str): Path to CSV file containing image coordinates.
    """
    df = pd.read_csv(csv_path)
    
    # Create scatter plot
    plt.figure(figsize=(12, 10))
    plt.scatter(df['Top_left_lon'], df['Top_left_lat'], alpha=0.5)
    
    # Add labels to the plot
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')
    plt.title('Grid Coverage of Satellite Images')
    plt.grid(True)
    
    # Display the plot
    plt.show()

def stitch_custom_area(csv_path, images_dir, output_path, top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon):
    """
    Stitches images for a custom defined area.
    
    Args:
        csv_path (str): Path to CSV file containing image coordinates.
        images_dir (str): Directory containing the satellite images.
        output_path (str): Path to save the stitched image.
        top_left_lat (float): Latitude of top-left corner.
        top_left_lon (float): Longitude of top-left corner.
        bottom_right_lat (float): Latitude of bottom-right corner.
        bottom_right_lon (float): Longitude of bottom-right corner.
    
    Returns:
        str: Path to the created stitched image.
    """
    # Read coordinates from CSV
    df = pd.read_csv(csv_path)
    
    # Filter for images within the specified area
    area_images = df[
        (df['Top_left_lat'] >= bottom_right_lat) & 
        (df['Bottom_right_lat'] <= top_left_lat) & 
        (df['Top_left_lon'] >= top_left_lon) & 
        (df['Bottom_right_lon'] <= bottom_right_lon)
    ]
    
    if area_images.empty:
        print("No images found in the specified area.")
        return None
    
    # Get unique latitude and longitude values within the area
    area_top_lats = sorted(area_images['Top_left_lat'].unique(), reverse=True)
    area_top_lons = sorted(area_images['Top_left_lon'].unique())
    
    # Calculate grid dimensions
    grid_height = len(area_top_lats)
    grid_width = len(area_top_lons)
    
    # Create a new blank image for the stitched result
    stitched_image = Image.new('RGB', (256 * grid_width, 256 * grid_height))
    
    # Dictionary to map coordinates to grid positions
    lat_to_row = {lat: i for i, lat in enumerate(area_top_lats)}
    lon_to_col = {lon: j for j, lon in enumerate(area_top_lons)}
    
    # Place each image in the correct position
    for _, row in area_images.iterrows():
        filename = row['Filename']
        top_lat = row['Top_left_lat']
        top_lon = row['Top_left_lon']
        
        img_path = os.path.join(images_dir, filename)
        
        if not os.path.exists(img_path):
            print(f"Warning: Image file not found: {img_path}")
            continue
        
        try:
            # Calculate position in the grid
            grid_row = lat_to_row[top_lat]
            grid_col = lon_to_col[top_lon]
            
            # Open the image and paste it into the right position
            img = Image.open(img_path)
            stitched_image.paste(img, (grid_col * 256, grid_row * 256))
        except Exception as e:
            print(f"Error processing {img_path}: {e}")
    
    # Save the stitched image
    stitched_image.save(output_path)
    print(f"Created custom area stitched image: {output_path}")
    
    return output_path

# Function to ensure all images in the CSV are used
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

# Example usage:
if __name__ == "__main__":
    # Example parameters (replace with your actual paths)
    csv_path = "./data/output/sat/map.csv"
    images_dir = "./data/output/sat/tiles/"
    output_dir = "./data/output/stitched"
    output_csv_path = "./data/output/stitched/map.csv"
    
    # Create 4x4 blocks (1024x1024 images) ensuring all images are used
    stitched_images = stitch_all_images(csv_path, images_dir, output_dir, block_size=4)
    print(f"Created {len(stitched_images)} stitched images.")
    
    # Create CSV with coordinates for the stitched images
    stitched_df = create_stitched_csv(csv_path, output_csv_path, block_size=4)
    print(f"CSV contains coordinates for {len(stitched_df)} stitched images.")
    
    # Visualize the grid coverage
    visualize_grid_coverage(csv_path)
    
    # Create a custom area stitch (optional)
    # stitch_custom_area(
    #     csv_path, 
    #     images_dir, 
    #     "custom_area.png", 
    #     46.843755, -91.995049,  # top-left coordinates
    #     46.842112, -91.990929   # bottom-right coordinates
    # )