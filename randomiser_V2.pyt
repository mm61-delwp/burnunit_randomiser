import arcpy, random, math, os, glob, csv, subprocess, zipfile
from datetime import datetime
from subprocess import Popen

class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the .pyt file)."""
        self.label = "Toolbox"
        self.alias = ""

        # List of tool classes associated with this toolbox
        self.tools = [FutureFireHistoryMaker, asciiToPhoenix]

class FutureFireHistoryMaker(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Future Fire History Maker"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""

        param0 = arcpy.Parameter(
            displayName="Input Features",
            name="in_features",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(displayName="Destination Directory",
            name="in_destination",
            datatype="DEFolder",
            direction="Input")

        param2 = arcpy.Parameter(
            displayName="Treatment Percentage",
            name="treat_perc",
            datatype="double",
            parameterType="Required",
            direction="Input")

        param3 = arcpy.Parameter(
            displayName="Replicates",
            name="n_replicates",
            datatype="long",
            parameterType="Required",
            direction="Input")

        param4 = arcpy.Parameter(
            displayName="Start Year",
            name="start_year",
            datatype="long",
            parameterType="Required",
            direction="Input")

        param5 = arcpy.Parameter(
            displayName="End Year",
            name="end_year",
            datatype="long",
            parameterType="Required",
            direction="Input")

        param6 = arcpy.Parameter(
            displayName="Randomise within zones",
            name="randomCheckbox",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")

        param7 = arcpy.Parameter(
            displayName="Include past fire history (Note: Slow! ~5 minutes per replicate)",
            name="fireHistCheckbox",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        
        param8 = arcpy.Parameter(
            displayName="Past Fire History",
            name="oldFirehist",
            datatype="DEFeatureClass",
            parameterType="Optional",
            direction="Input")

        param9 = arcpy.Parameter(
            displayName="Create Phoenix fire history .zip (Note: Slow! ~15 minutes per replicate)",
            name="runPhoenixCheckbox",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")

        param10 = arcpy.Parameter(displayName="Phoenix Data Converter location (directory)",
            name="pdc_location",
            datatype="DEFolder",
            parameterType="Optional",
            direction="Input")

        param11 = arcpy.Parameter(
            displayName="Run Phoenix Data Converter sessions concurrently",
            name="runConcurrentlyCheckbox",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")

        param12 = arcpy.Parameter(
            displayName="Delete temporary files (ASC, raster)",
            name="deleteTempCheckbox",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")

        params = [param0, param1, param2, param3, param4, param5, param6, param7, param8, param9, param10, param11, param12]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal validation is performed.  This method is called whenever a parameter has been changed."""
        if parameters[7].value == True: 
            # if the box is checked (true), enable parameter 8
            parameters[8].enabled = True
        else:
            parameters[8].enabled = False
        
        if parameters[9].value ==True:
            parameters[10].enabled = True
            parameters[11].enabled = True
            parameters[12].enabled = True
        else:
            parameters[10].enabled = False
            parameters[11].enabled = False
            parameters[12].enabled = False            
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        # Set environment & fix output extent to standard Phoenix data extent
        arcpy.env.outputCoordinateSystem = arcpy.SpatialReference("GDA 1994 VICGRID94")
        arcpy.env.extent = arcpy.Extent(2036000, 2251970, 2965280, 2842370)  # (XMin, YMin, XMax, YMax)

        # Turn the tool parameters into usable variables
        burnunits = parameters[0].valueAsText
        out_folder_path = parameters[1].valueAsText 
        treatmentPercentage = float(parameters[2].valueAsText)
        replicates = int(parameters[3].valueAsText)
        yearStart = int(parameters[4].valueAsText)
        yearFinish = int(parameters[5].valueAsText)
        fireHistory = parameters[8].valueAsText
        phoenixDataConverterLoc = parameters[10].valueAsText
        randomWithinZones = (False, True)[parameters[6].valueAsText == "true"]
        includeFireHistory = (False, True)[parameters[7].valueAsText == "true"]
        runPhoenixDataConverter = (False, True)[parameters[9].valueAsText == "true"]
        run_multiple_pdcs = (False, True)[parameters[11].valueAsText == "true"]
        delete_temporary_files = (False, True)[parameters[12].valueAsText == "true"]

        yearsSeries = yearFinish - yearStart

        arcpy.AddMessage("burnunits = " + burnunits)
        arcpy.AddMessage("out_folder_path = " + out_folder_path)
        arcpy.AddMessage("treatmentPercentage = " + str(treatmentPercentage))
        arcpy.AddMessage("replicates = " + str(replicates))
        arcpy.AddMessage("randomWithinZones = " + str(randomWithinZones))
        arcpy.AddMessage("includeFireHistory = " + str(includeFireHistory))
        arcpy.AddMessage("fireHistory = " + str(fireHistory))
        arcpy.AddMessage("runPhoenixDataConverter = " + str(runPhoenixDataConverter))
        arcpy.AddMessage("phoenixDataConverterLoc = " + str(phoenixDataConverterLoc))

        # Define shapefile attributes
        id_field = 'BUID'
        region_field = 'FIRE_REG'
        district_field = 'DISTRICT_N'
        zone_field = 'FireFMZ'
        grossarea_field = 'gross_ha'
        sort_field = 'sort'
        firetype_field = 'FIRETYPE'
        burndate_field = 'Burn_Date'
        timesincefire_field = 'TSF_2022'
        season_field = 'SEASON'

        firehistory_source_field = 'Source'

        zones = ['APZ', 'BMZ', 'LMZ', 'PBEZ']
        strPercentage = ('000' + (str(treatmentPercentage)).replace(".", "-"))[-4:]
        strZones = 'zones' if randomWithinZones else 'nozones'

        # Dictionary holding all district details including rotations & weighting for zone-weighted method
        ## Dictionary format ['DISTRICT NAME'] = ['Region Name', [minYrsAPZ, minYrsBMZ, minYrsLMZ], [maxYrsAPZ, maxYrsBMZ, maxYrsLMZ], zoneWeighting]
        districtDictionary = {}
        districtDictionary['FAR SOUTH WEST']    = ['Barwon South West',   [5, 8, 15],   [8, 20, 50],    0.65]
        districtDictionary['GOULBURN']          = ['Hume',                [6, 12, 15],  [8, 15, 50],    0.70]
        districtDictionary['LATROBE']           = ['Gippsland',           [5, 8, 15],   [8, 15, 50],    0.60]
        districtDictionary['MACALISTER']        = ['Gippsland',           [5, 8, 15],   [8, 15, 50],    0.60]
        districtDictionary['MALLEE']            = ['Loddon Mallee',       [5, 17, 15],  [12, 21, 50],   0.75]
        districtDictionary['METROPOLITAN']      = ['Port Phillip',        [5, 8, 15],   [8, 15, 50],    0.50]
        districtDictionary['MIDLANDS']          = ['Grampians',           [7, 12, 15],  [9, 14, 50],    0.75]
        districtDictionary['MURRAY GOLDFIELDS'] = ['Loddon Mallee',       [6, 12, 15],  [15, 30, 50],   0.50]
        districtDictionary['MURRINDINDI']       = ['Hume',                [5, 8, 15],   [12, 15, 50],   0.70]
        districtDictionary['OTWAY']             = ['Barwon South West',   [5, 8, 15],   [8, 13, 50],    0.65]
        districtDictionary['OVENS']             = ['Hume',                [9, 15, 15],  [11, 20, 50],   0.70]
        districtDictionary['SNOWY']             = ['Gippsland',           [5, 8, 15],   [8, 15, 50],    0.60]
        districtDictionary['TAMBO']             = ['Gippsland',           [5, 8, 15],   [8, 15, 50],    0.60]
        districtDictionary['UPPER MURRAY']      = ['Hume',                [9, 15, 15],  [11, 20, 50],   0.70]
        districtDictionary['WIMMERA']           = ['Grampians',           [6, 12, 15],  [8, 14, 50],    0.90]
        districtDictionary['YARRA']             = ['Port Phillip',        [5, 8, 15],   [8, 15, 50],    0.80]
        
        # Function to delete all parts of a shapefile
        def delete_shapefile(directory, shapefile_name):
            # remove path from shapefile_name if required
            shapefile_name = str(os.path.split(shapefile_name)[1])

            # make full path including directory
            shapefile = os.path.join(directory, shapefile_name)
   
            # find all parts of the shapefile
            files = glob.glob(os.path.splitext(shapefile)[0] + '.*')
            
            # and delete them
            for file in files:
                os.remove(file)

        # Function to add a new field to a shapefile if the field does not exist
        def add_field(shapefile, field_name, *args):
            # check if the field exists
            if arcpy.ListFields(shapefile, field_name): #if field exists, evaluates to true
                #arcpy.AddMessage(field_name + ' field exists in ' + str(shapefile))
                result = "exists"
            else:
                # Add a new field of that name   
                arcpy.AddField_management(shapefile, field_name, *args)
                arcpy.AddMessage(field_name + ' field missing from ' + str(shapefile) + '... adding')
                result = "added"
            return result

        # Function to create an empty copy of a shapefile or feature class
        def duplicate_empty_shapefile(input_shapefile, output_shapefile):

            # Copy the shapefile
            arcpy.CopyFeatures_management(input_shapefile, output_shapefile)

            # Delete all rows
            with arcpy.da.UpdateCursor(output_shapefile, [id_field]) as targetCursor:
                for row in targetCursor:
                    targetCursor.deleteRow()

        # Function to turn Burn_Date into SEASON
        def burndate_to_season(burnDate):
            #arcpy.AddMessage('burnDate: ' + str(burnDate))
            year, month = int(str(burnDate)[0:4]), int(str(burnDate)[4:6])
            if month <= 6:
                return int(year)
            else:
                return int(year) + 1

        # Create a copy of the input shapefile so we're not doing any editing directly in the source file, using file geodatabase to enable sorting of cursors
        newburnunits = out_folder_path + '\\' + os.path.split(burnunits)[1]
        if not arcpy.Exists(out_folder_path + "\\temp.gdb"):
            arcpy.CreateFileGDB_management(out_folder_path, "temp.gdb")
        newburnunits = out_folder_path + "\\temp.gdb\\burnunits"
        arcpy.CopyFeatures_management(burnunits, newburnunits)
        outputString = 'FireHistory_' + strPercentage + 'pc_' + strZones + '_' + str(yearStart) + 'to' + str(yearFinish)
        burnunits = newburnunits

        # Create a copy of the firehistory shapefile so we're not doing any editing directly in the source file, using file geodatabase
        if includeFireHistory:
            new_firehistory = out_folder_path + "\\temp.gdb\\firehistory"
            arcpy.CopyFeatures_management(fireHistory, new_firehistory)
            fireHistory = new_firehistory

        # Prepare the input shapefile
        add_field(burnunits, sort_field, "DOUBLE", 6, 4)
        add_field(burnunits, timesincefire_field, "LONG")
        add_field(burnunits, burndate_field, "LONG")
        add_field(burnunits, firetype_field, "STRING", 10)
        add_field(burnunits, season_field, "LONG")

        # populate FIRETYPE field (can't assume it's correct)
        with arcpy.da.UpdateCursor(burnunits, firetype_field) as cursor:
            for row in cursor:
                # set firetype to burn
                row[0] = "BURN"
                cursor.updateRow(row)

        # Create a CSV log file
        logfileName = (outputString + '_log.csv')
        logfile = open(os.path.join(out_folder_path, logfileName), 'w', newline='')
        writer = csv.writer(logfile)

        writer.writerow(["burnunits = " + str(parameters[0].valueAsText)])
        writer.writerow(["out_folder_path = " + str(out_folder_path)])
        writer.writerow(["treatmentPercentage = " + str(treatmentPercentage)])
        writer.writerow(["replicates = " + str(replicates)])
        writer.writerow(["yearStart:", yearStart, "yearFinish:", yearFinish])
        writer.writerow(["randomWithinZones = " + str(randomWithinZones)])
        writer.writerow(["includeFireHistory = " + str(includeFireHistory)])
        writer.writerow(["fireHistory = " + str(fireHistory)])
        writer.writerow(["runPhoenixDataConverter = " + str(runPhoenixDataConverter)])
        writer.writerow(["phoenixDataConverterLoc = " + str(phoenixDataConverterLoc)])
        writer.writerow(' ')
        writer.writerow(["District calculations table"])
        header =    ['district', 'region', 
                    'apz_total_ha', 'bmz_total_ha', 'lmz_total_ha', 'pbez_total_ha', 'fmz_ha', 
                    'apz_min_rot', 'apz_max_rot', 'bmz_min_rot', 'bmz_max_rot', 
                    'zone_weighting', 'random_weighting', 
                    'apz_annual_ha', 'bmz_annual_ha', 'lmz_annual_ha', 'district_annual_ha',
                    'apz_rot', 'bmz_rot', 'lmz_rot', 
                    'apz_prop', 'bmz_prop', 'lmz_prop'
                    ]
        writer.writerow(header)


        ### Calculate hectares and rotations per district and zone        
        arcpy.AddMessage("Calculating hectares and rotations")
        
        # Calculate hectare requirements
        for district in districtDictionary.keys():
            region = districtDictionary.get(district)[0]
            zoneArea = [0, 0, 0, 0]      # [APZ, BMZ, LMZ, PBEZ] selected hectares

            # Create an expression with proper delimiters
            expression = arcpy.AddFieldDelimiters(burnunits, district_field) + " = '" + district + "'"
            
            # Calculate gross hectares per zone - I'm sure there's a more efficient way to do this but it works!
            with arcpy.da.SearchCursor(burnunits, [id_field, region_field, district_field, zone_field, grossarea_field], where_clause=expression) as cursor:
                for row in cursor:
                    if row[3] == "APZ":
                        zoneArea[0] += row[4]
                    elif row[3] == "BMZ":
                        zoneArea[1] += row[4]
                    elif row[3] == "LMZ":
                        zoneArea[2] += row[4]
                    elif row[3] == "PBEZ":
                        zoneArea[3] += row[4]
            totalHectaresExPBEZ = sum(zoneArea) - zoneArea[3]

            # Determine the rotations and annual hectares required for each zone
            # Rotation is the number of years to divide the zone into, which is also the number of years between repeat treatments for each burn unit
            totalAnnualHectares = totalHectaresExPBEZ * (treatmentPercentage / 100)

            # Calculate requirements for random selection within districts. Also used to weight selection within zones.
            # Calculate rotation first as it must be an integer, which affects the annual hectares
            apzRotation = math.trunc(zoneArea[0] / (zoneArea[0] * (treatmentPercentage/100)))
            apzAnnualHectares = zoneArea[0] / apzRotation
            bmzRotation = math.trunc(zoneArea[1] / (zoneArea[1] * (treatmentPercentage/100)))
            bmzAnnualHectares = zoneArea[1] / bmzRotation
            lmzRotation = math.trunc(zoneArea[2] / (zoneArea[2] * (treatmentPercentage/100)))
            lmzAnnualHectares = zoneArea[2] / lmzRotation

            # Calculate requirements for selection within zones
            ## Get the Min and Max rotations for current district
            minRotation = districtDictionary.get(district)[1]
            maxRotation = districtDictionary.get(district)[2]

            # Now turn these into hectares and proportions
            minHa = [(zoneArea[0] / maxRotation[0]), (zoneArea[1] / maxRotation[1]), (zoneArea[2]/maxRotation[2])]
            maxHa = [(zoneArea[0] / minRotation[0]), (zoneArea[1] / minRotation[1]), (zoneArea[2]/minRotation[2])]
            minHaApzBmz = minHa[0] + minHa[1]
            minHaApzBmzLmz = minHa[0] + minHa[1] + minHa[2]
            proportionMinHaApzBmz = [(minHa[0] / minHaApzBmz), (minHa[1] / minHaApzBmz)]
            proportionMinHaApzBmzLmz = [(minHa[0] / minHaApzBmzLmz), (minHa[1] / minHaApzBmzLmz), (minHa[2] / minHaApzBmzLmz)]
            setProportionWithoutZones = [(apzAnnualHectares / totalAnnualHectares), (bmzAnnualHectares / totalAnnualHectares), (lmzAnnualHectares / totalAnnualHectares)]

            if randomWithinZones:
                # Is annual hectares < required to treat APZ & BMZ at minimum rotation?
                if totalAnnualHectares <= minHaApzBmz:
                    apzAnnualHectares = totalAnnualHectares * proportionMinHaApzBmz[0]
                    bmzAnnualHectares = totalAnnualHectares * proportionMinHaApzBmz[1]
                    lmzAnnualHectares = 1
                    setProportionZones = [(apzAnnualHectares/totalAnnualHectares), (bmzAnnualHectares/totalAnnualHectares), (lmzAnnualHectares/totalAnnualHectares)]
                else:
                    # APZ and BMZ can't be pushed past their minimum rotation (max ha), so hectares are proportionally allocated across all 3 zones until these limits are reached, then sent to LMZ
                    apzAnnualHectares = min(maxHa[0], minHa[0] + (totalAnnualHectares - minHaApzBmz) * proportionMinHaApzBmzLmz[0])
                    bmzAnnualHectares = min(maxHa[1], minHa[1] + (totalAnnualHectares - minHaApzBmz) * proportionMinHaApzBmzLmz[1])
                    lmzAnnualHectares = totalAnnualHectares - (apzAnnualHectares + bmzAnnualHectares)
                    setProportionZones = [(apzAnnualHectares/totalAnnualHectares), (bmzAnnualHectares/totalAnnualHectares), (lmzAnnualHectares/totalAnnualHectares)]
                
                # Now we weight these to produce something between full random within zones and random without zones
                zonalWeighting = districtDictionary.get(district)[3]    # pulls zone weighting from table
                setProportionWeighted =     [(setProportionWithoutZones[0] * (1 - zonalWeighting) + setProportionZones[0] * zonalWeighting), 
                                            (setProportionWithoutZones[1] * (1 - zonalWeighting) + setProportionZones[1] * zonalWeighting),
                                            (setProportionWithoutZones[2] * (1 - zonalWeighting) + setProportionZones[2] * zonalWeighting)]
                tempTotal = setProportionWeighted[0] + setProportionWeighted[1] + setProportionWeighted[2]
                setProportion = [setProportionWeighted[0] * tempTotal, setProportionWeighted[1] * tempTotal, setProportionWeighted[2] * tempTotal]

                # Use these proportions to calculate annual hectare requirements & rotations
                apzRotation = math.trunc(zoneArea[0]/apzAnnualHectares)
                apzAnnualHectares = zoneArea[0] / apzRotation
                bmzRotation = math.trunc(zoneArea[1]/bmzAnnualHectares)
                bmzAnnualHectares = zoneArea[1] / bmzRotation
                lmzRotation = math.trunc(zoneArea[2]/lmzAnnualHectares)
                lmzAnnualHectares = zoneArea[2] / lmzRotation

            # Send hectares and rotations to district dictionary
            districtDictionary[district].append([apzAnnualHectares, bmzAnnualHectares, lmzAnnualHectares])
            districtDictionary[district].append([apzRotation, bmzRotation, lmzRotation])

            # Send some information to the geoprocessing messages screen, but only do it once.
            arcpy.AddMessage(   district + ", " + region + ": " \
                                + str(int(apzAnnualHectares)) + "ha/yr APZ, " + str(int(bmzAnnualHectares)) + "ha/yr BMZ, "  + str(int(lmzAnnualHectares)) + "ha/yr LMZ, " \
                                + "(Rotation: " + str(apzRotation) + "/" + str(bmzRotation) + "/" + str(lmzRotation) + "yrs, " \
                                + str(round(setProportion[0]* 100, 1)) + "/" + str(round(setProportion[1] * 100, 1)) + "/" + str(round(setProportion[2] * 100, 1)) + "%)")

            # Send same information to the logfile
            row =   [district, region, 
                    round(zoneArea[0], 1), round(zoneArea[1], 1), round(zoneArea[2], 1), round(zoneArea[3], 1), round(sum(zoneArea), 1),
                    districtDictionary.get(district)[1][0], districtDictionary.get(district)[2][0],
                    districtDictionary.get(district)[1][1], districtDictionary.get(district)[2][1],
                    districtDictionary.get(district)[3], 1 - districtDictionary.get(district)[3],
                    round(apzAnnualHectares,1), round(bmzAnnualHectares, 1), round(lmzAnnualHectares, 1), round(totalAnnualHectares, 1),
                    apzRotation, bmzRotation, lmzRotation, 
                    round(setProportion[0]* 100, 1), round(setProportion[1] * 100, 1), round(setProportion[2] * 100, 1)
                    ]
            writer.writerow(row)


        ### Make burn schedule shapefiles
        for replicate in range (1, replicates + 1):
            arcpy.AddMessage("Creating burn schedule for " + str(yearStart) + " to " + str(yearFinish) + " - replicate " + str(replicate))

            # Duplicate the burn units layer then empty it out (so we've got a shapefile to dump stuff in later)
            strReplicate = ('0' + str(replicate))[-2:]
            burnunits_output = os.path.join(out_folder_path, outputString) + '_r' + strReplicate +'.shp'
            
            duplicate_empty_shapefile(burnunits, burnunits_output)

            # Make a list of fields in the shapefile
            lstFields = [field.name for field in arcpy.ListFields(burnunits_output) if field.type not in ['Geometry']]

            # Remove problematic fields by matching prefixes
            bad_fields =['FID', 'Shape_']   # catch all variations e.g. 'Shape_Le_1', 'Shape_Leng' ..., which various GIS might truncate 'Shape_Length' to for shapefile. 
            lstFields = [field_name for field_name in lstFields if not any (bad_field in field_name for bad_field in bad_fields)]

            # Sort field list by slicing to ensure first field is sort_field - this enables sorting of cursors later
            sort_field_position = lstFields.index(sort_field)
            lstFields = lstFields[sort_field_position:] + lstFields[:sort_field_position]

            # Add geometry
            lstFields.append("SHAPE@") 

            # populate sort field with random values
            with arcpy.da.UpdateCursor(burnunits, [sort_field]) as cursor:
                for row in cursor:
                    row[0] = random.random()
                    cursor.updateRow(row)
            
            # Calculate hectare requirements and produce output shapefiles
            for district in districtDictionary.keys():
                region = districtDictionary.get(district)[0]
                zonesAnnualHectares = districtDictionary.get(district)[4]
                zonesRotations = districtDictionary.get(district)[5]
                minRotation = districtDictionary.get(district)[1]
                maxRotation = districtDictionary.get(district)[2]

                for zone in ["APZ", "BMZ", "LMZ"]:
                    expression = arcpy.AddFieldDelimiters(burnunits, district_field) + " = '" + district + "' AND " + arcpy.AddFieldDelimiters(burnunits, zone_field) + " = '" + zone + "' ORDER BY " + arcpy.AddFieldDelimiters(burnunits, sort_field)

                    if zone == "APZ":
                        zoneAnnualHectares = zonesAnnualHectares[0]
                        zoneRotation = zonesRotations[0]
                        zoneMinimumYears = minRotation[0]
                    elif zone == "BMZ":
                        zoneAnnualHectares = zonesAnnualHectares[1]
                        zoneRotation = zonesRotations[1]
                        zoneMinimumYears = minRotation[1]
                    elif zone == "LMZ":
                        zoneAnnualHectares = zonesAnnualHectares[2]
                        zoneRotation = zonesRotations[2]
                        zoneMinimumYears = minRotation[2]
                    
                    with arcpy.da.InsertCursor(burnunits_output, lstFields) as outputCursor:
                        with arcpy.da.UpdateCursor(burnunits, lstFields, where_clause=expression) as cursor: # The order of values in the list matches the order of fields specified by the field_names argument.
                            currentYear = 0
                            currentHa = 0
                            for row in cursor:

                                # add gross burn unit are to currentHa
                                currentHa += row[lstFields.index(grossarea_field)]

                                # send a copy of this polygon to the output shapefile for each repeat
                                while currentYear <= yearsSeries:

                                    if row[lstFields.index(timesincefire_field)] is None or (row[lstFields.index(timesincefire_field)] + currentYear) >= zoneMinimumYears: 
                                        # ^ This removes in a rather crude way any burning below minimum rotation. The burn unit will still proceed to later repeats. Evaluates to true if TSF field is null.

                                        # set burn date
                                        burnDate = (yearStart + currentYear) * 10000 + 401
                                        row[lstFields.index(burndate_field)] = burnDate

                                        # set season
                                        season = burndate_to_season(burnDate)
                                        row[lstFields.index(season_field)] = season

                                        cursor.updateRow(row) 

                                        fieldValues = []
                                        for field in row:
                                            fieldValues.append(field)
                                        
                                        outputCursor.insertRow(fieldValues)
                                    
                                    # go to next repeat
                                    currentYear += zoneRotation 

                                # determine which year we are now in
                                currentYear = math.floor(currentHa / zoneAnnualHectares)

            # Add additional table to log file detailing actual annual hectares per district & Zone
            # District, Region, FMZ, Replicate, [Year1], [Year2], ...
            #      ...,    ..., ...,       ...,      Ha,      Ha, ...
            if replicate == 1:
                writer.writerow(' ')    # leave space between tables
                writer.writerow(["Annual gross hectares per district & zone"])   # table name

                # Write header row
                table_headers = ['District', 'Region', 'FMZ', 'Replicate'] + [*range(yearStart, yearFinish + 1)]     # asterix is unpacking operator 
                writer.writerow(table_headers)
            
            # Calculate hectares
            for district in districtDictionary.keys():
                for zone in ["APZ", "BMZ", "LMZ"]:
                    region = districtDictionary.get(district)[0]
                    table_row = [district, region, zone, replicate]
                    for season in range(yearStart, yearFinish + 1):
                        
                        # Create an expression with proper delimiters
                        expression = arcpy.AddFieldDelimiters(burnunits, district_field) + " = '" + district + "' AND " + arcpy.AddFieldDelimiters(burnunits, zone_field) + " = '" + zone + "' AND " + arcpy.AddFieldDelimiters(burnunits, season_field) + " = " + str(season) 
                        
                        # Sum hectares
                        area_ha = 0
                        with arcpy.da.SearchCursor(burnunits_output, [id_field, region_field, district_field, zone_field, grossarea_field], where_clause=expression) as cursor:
                            for row in cursor:
                                area_ha += row[4]
                        
                        table_row.append(area_ha)
                    
                    # Write to log
                    writer.writerow(table_row)


        ### Incorporate past fire history -- Completely skips this bit if no fire history is provided
        if includeFireHistory: 

            # Make a list of fields in the fire history shapefile
            lstFields_fireHistory = [field.name for field in arcpy.ListFields(fireHistory) if field.type not in ['Geometry']]
            lstFields_fireHistory.append("SHAPE@") # add the full Geometry object

            ## Add necessary fields to fire history shapefile
            add_field(fireHistory, burndate_field, "LONG")
            season_checkexist = add_field(fireHistory, season_field, "LONG")
            firetype_checkexist = add_field(fireHistory, firetype_field, "STRING", 10)

            # Populate FIRETYPE field from Source and SEASON from Burn_Date
            with arcpy.da.UpdateCursor(fireHistory, lstFields_fireHistory) as cursor:
                for row in cursor:
                    needs_update = False
                    sourceValue = row[lstFields_fireHistory.index(firehistory_source_field)]
                    burndateValue = row[lstFields_fireHistory.index(burndate_field)]
                    
                    # speed things up by only updating rows if required
                    if season_checkexist == "added":
                        seasonValue = burndate_to_season(burndateValue)
                        needs_update = True
                    if firetype_checkexist == "added":
                        if sourceValue == 'Burns':
                            row[lstFields_fireHistory.index(firetype_field)] = 'BURN'
                        else:
                            row[lstFields_fireHistory.index(firetype_field)] = 'BUSHFIRE'
                        
                        row[lstFields_fireHistory.index(season_field)] = seasonValue
                        needs_update = True
                    if needs_update:
                        cursor.updateRow(row)


            # Merge shapefiles, retaining only FIRETYPE, Burn_Date and SEASON
            for replicate in range (1, replicates + 1):
                arcpy.AddMessage('Joining fire history to replicate ' + str(replicate))

                strReplicate = ('0' + str(replicate))[-2:]
                burnunits_output = os.path.join(out_folder_path, outputString) + '_r' + strReplicate +'.shp'

                # Map fields for merge
                field_mappings = arcpy.FieldMappings()
                for field in [burndate_field, firetype_field, season_field]:
                    field_map = arcpy.FieldMap()
                    field_map.addInputField(fireHistory, field) 
                    field_map.addInputField(burnunits_output, field)
                    field_mappings.addFieldMap(field_map)

                # do the merge
                trim = os.path.splitext(burnunits_output)[0]
                merged_output = trim + '_merged.shp'
                arcpy.Merge_management([fireHistory, burnunits_output], merged_output, field_mappings)

                # create zipfile for storage & transport
                shapefile_parts_list = [trim + '_merged.shp', trim + '_merged.shx', trim + '_merged.dbf', trim + '_merged.prj']
                zipfile_name = trim + '_FAME.zip'
                with zipfile.ZipFile(zipfile_name, 'w', compression=zipfile.ZIP_DEFLATED) as zipObj: 
                    for shapefile_part in shapefile_parts_list:
                        zipObj.write(shapefile_part, os.path.split(shapefile_part)[1])


        ### Create rasters (split out Phoenix data converter so ASCII files will be produced even if data converter fails)
        if runPhoenixDataConverter:
            list_output_asciis = []
            for replicate in range (1, replicates + 1):

                # set up correct file names and paths
                strReplicate = ('0' + str(replicate))[-2:]
                burnunits_output = os.path.join(out_folder_path, outputString) + '_r' + strReplicate +'.shp'
                trim = os.path.splitext(burnunits_output)[0]
                
                # selects whether to use _merged.shp or regular, - did user ask for merge or not?
                if includeFireHistory:
                    input_shapefile = trim + '_merged.shp'
                else:
                    input_shapefile = trim + '.shp'

                temp_raster = 'temp_raster'
                temp_ascii = trim + '.ASC'
                cell_size = 30

                arcpy.AddMessage('Converting to Raster then ASCII. Warning: Slow! - replicate ' + str(replicate))
                arcpy.PolygonToRaster_conversion(input_shapefile, burndate_field, temp_raster, 'MAXIMUM_AREA', burndate_field, cell_size)
                arcpy.RasterToASCII_conversion(temp_raster, temp_ascii)

                list_output_asciis.append(temp_ascii)

                if delete_temporary_files:
                    arcpy.Delete_management(temp_raster)

        ### Run Phoenix Data Converter
        if runPhoenixDataConverter:
            list_pdc_strings = []
            for ascii in list_output_asciis:
                phoenix_output = os.path.splitext(ascii)[0] + '_Phoenix.zip'

                cell_size = 30
                dateString = (str(yearFinish) + '-06-30')
                
                # Example command line: "C:\Data\Phoenix\scripts\Phoenix Data Converter.exe" D:\Projects\20220202_Risk2_TargetSetting\bu_scheduler\outputs\burnunits_v2_12-0pc_zones_2020to2040_r01.ASC D:\Projects\20220202_Risk2_TargetSetting\bu_scheduler\outputs\burnunits_v2_12-0pc_zones_2020to2040_r01 30 2040-06-30
                pdc_string = (phoenixDataConverterLoc + '\Phoenix Data Converter.exe ' + str(ascii) + ' ' + str(phoenix_output) + ' ' + str(cell_size) + ' ' + str(dateString))

                if not run_multiple_pdcs:
                    arcpy.AddMessage('Converting ASCII to Phoenix data files. Warning: Slow! - replicate ' + str(replicate))
                    subprocess.call(pdc_string)
                else:
                    list_pdc_strings.append(pdc_string)

            if run_multiple_pdcs:
                arcpy.AddMessage('Converting ' +str(len(list_pdc_strings)) + ' ASCIIs to Phoenix data files. Warning: Slow')
                procs = [ Popen(i) for i in list_pdc_strings ]
                for p in procs:
                    p.wait()

            # Clean up unwanted files
            if delete_temporary_files:
                for ascii in list_output_asciis:
                    os.remove(ascii)

        # Delete the burnunits_sorted feature class
        if delete_temporary_files: 
            delete_shapefile(out_folder_path, burnunits)

        # Close the logfile
        logfile.close()

        return






class asciiToPhoenix(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Convert ASCII files to Phoenix Fire History"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""

        parameter0 = arcpy.Parameter(
            displayName="Input ASCIIs",
            name="in_asciis",
            datatype="DEFile",
            parameterType="Required",
            direction="Input",
            multiValue=True)
        
        parameter1 = arcpy.Parameter(
            displayName="History Current At Year",
            name="treat_perc",
            datatype="GPLong",
            parameterType="Required",
            direction="Input")

        parameter2 = arcpy.Parameter(displayName="Phoenix Data Converter location (directory)",
            name="pdc_location",
            datatype="DEFolder",
            parameterType="Optional",
            direction="Input")

        parameter3 = arcpy.Parameter(
            displayName="Run Phoenix Data Converter sessions concurrently",
            name="runConcurrentlyCheckbox",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
            
        parameter0.filter.list = ['ASC']
        params = [parameter0, parameter1, parameter2, parameter3]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal validation is performed.  This method is called whenever a parameter has been changed."""        
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        # Set environment & fix output extent to standard Phoenix data extent
        arcpy.env.outputCoordinateSystem = arcpy.SpatialReference("GDA 1994 VICGRID94")
        arcpy.env.extent = arcpy.Extent(2036000, 2253570, 2965280, 2842370)  # (XMin, YMin, XMax, YMax) # updated to match fuel extent per Andrew Blackett's change

        # Turn the tool parameters into usable variables
        ascii_list = parameters[0].valueAsText
        yearFinish = int(parameters[1].valueAsText)
        phoenixDataConverterLoc = parameters[2].valueAsText
        run_multiple_pdcs = (False, True)[parameters[3].valueAsText == "true"]

        arcpy.AddMessage("ascii_list = " + str(ascii_list))
        arcpy.AddMessage("yearFinish = " + str(yearFinish))
        arcpy.AddMessage("phoenixDataConverterLoc = " + str(phoenixDataConverterLoc))
        arcpy.AddMessage("run_multiple_pdcs = " + str(run_multiple_pdcs))

        list_pdc_strings = []

        for ascii in ascii_list.split(';'):                  
            phoenix_output = os.path.splitext(ascii)[0] + '_Phoenix.zip'

            cell_size = 30
            dateString = (str(yearFinish) + '-06-30')
            
            # Example command line: "C:\Data\Phoenix\scripts\Phoenix Data Converter.exe" D:\Projects\20220202_Risk2_TargetSetting\bu_scheduler\outputs\burnunits_v2_12-0pc_zones_2020to2040_r01.ASC D:\Projects\20220202_Risk2_TargetSetting\bu_scheduler\outputs\burnunits_v2_12-0pc_zones_2020to2040_r01 30 2040-06-30
            pdc_string = (phoenixDataConverterLoc + '\Phoenix Data Converter.exe ' + str(ascii) + ' ' + str(phoenix_output) + ' ' + str(cell_size) + ' ' + str(dateString))

            if not run_multiple_pdcs:
                arcpy.AddMessage('Converting ASCII to Phoenix data files. Warning: Slow! - ' + str(ascii))
                subprocess.call(pdc_string)
            else:
                list_pdc_strings.append(pdc_string)

        if run_multiple_pdcs:
            arcpy.AddMessage('Converting ' +str(len(list_pdc_strings)) + ' ASCIIs to Phoenix data files. Warning: Slow')
            procs = [ Popen(i) for i in list_pdc_strings ]
            for p in procs:
                p.wait()

        return
