#!/usr/bin/env python3

import os
import sys
import logging
from datetime import datetime
import time
import requests

import geopandas as gpd
from shapely.geometry import shape
from shapely.geometry import Polygon
from shapely.geometry import Point
from shapely import wkt
from shapely.geometry import JOIN_STYLE
import matplotlib.pyplot as plt 

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
API_URL = "https://deepstatemap.live/api/history/last"
OUTPUT_DIR = "data"
OUTPUT_FILENAME = f"deepstatemap_data_{datetime.now().strftime('%Y%m%d')}.geojson"
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


def make_api_request():
    """Make a request to the API and return the JSON response."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows Phone 10.0; Android 6.0.1; Microsoft; RM-1152) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/52.0.2743.116 Mobile Safari/537.36 Edge/15.15254"
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(API_URL, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"API request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error("All API request attempts failed.")
                sys.exit(1)


def process_data(data):
    """Process the API response data."""

    geo_list = []
    for f in data['map']['features']:
        geom = f['geometry']
        name = f['properties']['name']
        new_feature = {
            "name":name,
            "geometry":wkt.loads(wkt.dumps(shape(geom), output_dimension=2))
            }

        geo_list.append(new_feature)
        
    # Split the name by '///' and take the first part
    def extract_first_part(name, part=0):
        first_part = name.split('///')[part].strip()
        return first_part
    
    for item in geo_list:
        item['name'] = extract_first_part(item['name'], part=1)
    
    return geo_list


def create_geodataframe(geo_list):
    """Create a GeoDataFrame from the processed data."""
    raw_gdf = gpd.GeoDataFrame(geo_list).set_crs(4326)
    
    mask = raw_gdf.geometry.apply(lambda x: isinstance(x, Polygon))
    polygon_gdf = raw_gdf[mask]
    
    filtered_gdf = polygon_gdf[polygon_gdf['name'].isin(['CADR and CALR', 'Occupied', 'Occupied Crimea'])].reset_index()
    
    merged_gdf = gpd.GeoSeries(filtered_gdf.union_all(), crs=4326)
    
    # Applying buffer to remove union artifacts
    eps = 0.000009

    deartifacted_gdf = (
        merged_gdf
        .buffer(eps, 1, join_style=JOIN_STYLE.mitre)
        .buffer(-eps, 1, join_style=JOIN_STYLE.mitre)
        )
    
    return deartifacted_gdf


def main():
    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Make API request
    logger.info("Making API request...")
    raw_data = make_api_request()
    
    # Process data
    logger.info("Processing data...")
    processed_data = process_data(raw_data)
    
    # Create GeoDataFrame
    logger.info("Creating GeoDataFrame...")
    gdf = create_geodataframe(processed_data)
    
    # Export as GeoJSON
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)
    logger.info(f"Exporting data to {output_path}...")
    gdf.to_file(output_path, driver="GeoJSON")
    
    logger.info("Data update completed successfully.")

if __name__ == "__main__":
    main()