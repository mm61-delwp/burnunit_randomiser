# Burn Unit Randomiser


Randomly selects burn units from supplied shapefile to produce a burn schedule for any requested annual treatment percentage

![image_tool](https://user-images.githubusercontent.com/100050237/155258591-4d5f0bc6-c78d-4c4f-805b-8b5ed7d30e2d.JPG)

## Usage
1. Download [randomiser.pyt](https://github.com/mm61-delwp/burnunit_randomiser/blob/main/randomiser.pyt) and burn units shapefile
2. Drop the .pyt into ArcGIS Pro catalogue window
3. Run it

## Outputs

Each replicate will produce 2 shapefiles:
* [burn unit input file]_[annual treatment %]_[zones/noZones]_[replicate].shp = overlapping fire history for FAME etc.
* [burn unit input file]_[annual treatment %]_[zones/noZones]_[replicate]_phx.shp = Phoenix LASTBURNT-type fire history
