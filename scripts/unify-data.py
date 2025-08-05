#!/usr/bin/env python3

import os
import sys
import logging
from datetime import datetime
# from datetime import timedelta # for potential script re-runs (debug)
import gzip
from io import StringIO

# Prevent "GDAL_DATA is not defined" warning (has to be set before importing geo libraries)
os.environ['GDAL_DATA'] = os.path.join(f'{os.sep}'.join(sys.executable.split(os.sep)[:-1]), 'Library', 'share', 'gdal')

import geopandas as gpd
from fiona._err import CPLE_OpenFailedError


# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
CURRENT_DATE = datetime.now()
# CURRENT_DATE = datetime.now() - timedelta(days=3) # for potential script re-runs (debug)
CRS = "EPSG:4326"

SOURCE_FILE = f"deepstatemap_data_{CURRENT_DATE.strftime('%Y%m%d')}.geojson"
SOURCE_FILE_PATH = os.path.join("data", SOURCE_FILE)

TARGET_FILE = "deepstate-map-data.geojson.gz"
TARGET_FILE_PATH = os.path.join(TARGET_FILE)


def check_source_geojson_existence():
    """Checks if a new GeoJSON file exists in the specified folder."""

    if os.path.isfile(SOURCE_FILE_PATH):
        logger.info("Source GeoJSON exists.")
    else:
        logger.error(f"Exiting because source GeoJSON with {CURRENT_DATE.strftime('%Y-%m-%d')} update doesn't exist.")
        sys.exit(1)


def check_target_geojson_existence():
    """Checks if compressed GeoJSON file exists in the repository root."""

    if os.path.isfile(TARGET_FILE_PATH):
        logger.info("Target GeoJSON exists.")
    else:
        logger.error("Exiting because target GeoJSON doesn't exist.")
        sys.exit(1)


def import_source_geojson():
    """Imports updated GeoJSON geometry into GeoDataFrame"""

    try:
        # Use 'pyogrio' engine to read geojson (improved performance)
        new_rows_gdf = gpd.read_file(SOURCE_FILE_PATH, engine="pyogrio")

    except (ValueError, NotImplementedError) as e:
        logger.warning("Could not use 'pyogrio' engine, switching to 'fiona'...")
        # Use 'fiona' engine to read geojson (more robust)
        new_rows_gdf = gpd.read_file(SOURCE_FILE_PATH, engine="fiona")

    except Exception as e:
        logger.error("Exiting due to error while importing source GeoJSON: {e}")
        sys.exit(1)

    # Append dictionary with date and geometry to a list
    new_rows = []
    if new_rows_gdf.empty:
        logger.warning("Exiting due to empty GeoDataFrame.")
        sys.exit(1)
    else:
        new_rows.append({
            "date": CURRENT_DATE.strftime('%Y-%m-%d'),
            "geometry": new_rows_gdf.geometry.iloc[0]
        })
        # Validate if source file contains single feature (row)
        if new_rows_gdf.shape[0] > 1:
            logger.error(f"Exiting because expected 1 feature, but source GeoJSON contains {new_rows_gdf.shape[0]}.")
            sys.exit(1)

    try:
        # Convert list of dictionaries into GeoDataFrame  
        source_gdf = gpd.GeoDataFrame(new_rows, geometry="geometry", crs=CRS)
        logger.info(f"Successfully imported {source_gdf.shape[0]} feature(-s) into GeoDataFrame. Update for {CURRENT_DATE.strftime('%Y-%m-%d')}.")
        return source_gdf
    
    except CPLE_OpenFailedError as f:
        logger.error(f"Exiting because expected list with dictionary, but received an unsupported file format: {f}")
        sys.exit(1)

    except Exception as e:
        logger.error(f"Exiting due to error while loading dictionary into GeoDataFrame: {e}")
        sys.exit(1)


def import_target_geojson():
    """Imports compressed GeoJSON with consolidated records into GeoDataFrame."""

    # Store target (compressed) GeaJSON contents as GeoJSON string
    with gzip.open(TARGET_FILE_PATH, "rt", encoding="utf-8") as f:
        geojson_str = f.read()
        
    try:
        # Read GeoJSON string into GeoDataFrame
        target_gdf = gpd.read_file(StringIO(geojson_str), crs=CRS)
        logger.info(f"Successfully imported target GeoJSON. Last update: {target_gdf.iloc[-1,1]}. Current GeoDataFrame shape: {target_gdf.shape}.")
        return target_gdf.drop(columns="id")
    
    except Exception as e:
        logger.error(f"Exiting due to error while loading GeoJSON string into GeoDataFrame: {e}")
        sys.exit(1)


def unify_datasets(existing_dataset, new_row):
    """Concatenates target (multiple geometries) and source (single geometry) GeoDataFrames."""

    # Check if 'last' date values match in both GeoDataFrames 
    if new_row.iloc[-1].loc["date"] in existing_dataset["date"].values:
        logger.warning(f"Exiting because target dataset already contains the {CURRENT_DATE.strftime('%Y-%m-%d')} update.")
        sys.exit(1)  
    else:
        logger.info("Current update does not yet exist in the target dataset.")
        try:
            # Ensure a natural continuation of index for new data
            new_row.index = [existing_dataset.index.max() + 1]
            # Concatenate 2 datasets (update appends to the bottom/end of the target)
            unified_gdf = gpd.pd.concat(
                [existing_dataset, new_row],
                ignore_index=False,
                copy=False
                )
            logger.info(f"Successfully concatenated the existing and new data. New GeoDataFrame shape: {unified_gdf.shape}.")
            return unified_gdf
        
        except Exception as e:
            logger.error(f"Exiting due to error during GeoDataFrames concatenation: {e}")
            sys.exit(1)


def compress_gdf(unified_gdf):
    """Converts unified GeoDataFrame into JSON stirng, and writes it into a compressed GeoJSON file."""

    # Convert unified GeoDataFrame into a GeoJSON string
    geojson_str = unified_gdf.to_json()

    try:
        # Write GeoJSON string into a gzip compressed file 
        with gzip.open(TARGET_FILE, "wt", encoding="utf-8") as f:
            f.write(geojson_str)
        logger.info(f"Successfully exported '{TARGET_FILE}' to the project root.")

    except Exception as e:
        logger.warning(f"Exiting due to error while writing GeoJSON string into file: {e}")
        sys.exit(1)


def main():

    # Ensure source (updated data) file exists
    logger.info("Checking if source GeoJSON exists...")
    check_source_geojson_existence()

    # Ensure target (compressed dataset) file exists
    logger.info("Checking if target GeoJSON exists...")
    check_target_geojson_existence()
    
    # Import source data
    logger.info("Importing source GeoJSON...")
    new_row = import_source_geojson()
    
    # Import target data
    logger.info("Importing target GeoJSON...")
    existing_dataset = import_target_geojson()
    
    # Concatenate dataests into a single GeoDataFrame
    logger.info("Concatenating source and target datasets...")
    unified_gdf = unify_datasets(existing_dataset, new_row)
    
    # Export unified dataset into a compressed GeoJSON file
    logger.info("Exporting unified dataset into a compressed file...")
    compress_gdf(unified_gdf)

if __name__ == "__main__":
    main()