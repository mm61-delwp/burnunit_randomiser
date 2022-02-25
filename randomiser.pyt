# -*- coding: utf-8 -*-

import arcpy, random, math, os, glob, csv, subprocess
from datetime import datetime


class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the .pyt file)."""
        self.label = "Toolbox"
        self.alias = ""

        # List of tool classes associated with this toolbox
        self.tools = [Tool]


class Tool(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Phoenix Future Fire History Maker"
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

        param1 = arcpy.Parameter(displayName="Destination Folder",
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
            displayName="Include past fire history (Note: this is slow!)",
            name="fireHistCheckbox",
            datatype="GPBoolean",
            parameterType="Required",
            direction="Input")
        
        param8 = arcpy.Parameter(
            displayName="Past Fire History",
            name="oldFirehist",
            datatype="DEFeatureClass",
            parameterType="Optional",
            direction="Input")

        param9 = arcpy.Parameter(
            displayName="Create Phoenix fire history .zip (Note: this is slow!)",
            name="runPhoenixCheckbox",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")

        param10 = arcpy.Parameter(displayName="Phoenix Data Converter location (directory)",
            name="pdc_location",
            datatype="DEFolder",
            direction="Input")


        params = [param0, param1, param2, param3, param4, param5, param6, param7, param8, param9, param10]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal validation is performed.  This method is called whenever a parameter has been changed."""
        if parameters[7].value == True: 
            # if the box is checked (true), enable parameter 8
            parameters[8].enabled = True
            parameters[9].enabled = True
            if parameters[9].value ==True:
                parameters[10].enabled = True
        else:
            parameters[8].enabled = False
            parameters[9].enabled = False
            parameters[10].enabled = False
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        # Set environment & fix output extent to standard Phoenix data extent
        arcpy.env.outputCoordinateSystem = arcpy.SpatialReference("GDA 1994 VICGRID94")
        arcpy.env.extent = arcpy.Extent(2036000, 2251970, 2965280, 2842370)

        # Turn the tool parameters into usable variables
        burnunits = parameters[0].valueAsText
        out_folder_path = parameters[1].valueAsText 
        treatmentPercentage = float(parameters[2].valueAsText)
        replicates = int(parameters[3].valueAsText)
        yearStart = int(parameters[4].valueAsText)
        yearFinish = int(parameters[5].valueAsText)
        randomChecked = parameters[6].valueAsText
        fireHistChecked = parameters[7].valueAsText
        fireHistory = parameters[8].valueAsText or "none"
        runPdcChecked = randomChecked = parameters[9].valueAsText
        phoenixDataConverterLoc = parameters[10].valueAsText 
        if randomChecked == "true":
            randomWithinZones = True
        else:
            randomWithinZones = False
        if fireHistChecked == "true":
            includeFireHistory = True
        else:
            includeFireHistory = False
        if runPdcChecked == "true":
            runPhoenixDataConverter = True
        else:
            runPhoenixDataConverter = False
        yearsSeries = yearFinish - yearStart

        arcpy.AddMessage("burnunits = " + burnunits)
        arcpy.AddMessage("out_folder_path = " + out_folder_path)
        arcpy.AddMessage("treatmentPercentage = " + str(treatmentPercentage))
        arcpy.AddMessage("replicates = " + str(replicates))
        arcpy.AddMessage("randomWithinZones = " + str(randomWithinZones))
        arcpy.AddMessage("includeFireHistory = " + str(includeFireHistory))
        arcpy.AddMessage("fireHistory = " + str(fireHistory))

        # Define shapefile attributes
        id_field = 'BUID'
        region_field = 'DELWP_REGI'
        district_field = 'DISTRICT_N'
        zone_field = 'FireFMZ'
        grossarea_field = 'AreaHa'
        sort_field = 'sort'
        firetype_field = 'FIRETYPE'
        burndate_field = 'Burn_Date'
        timesincefire_field = 'TSF'
        season_field = 'SEASON'

        zones = ['APZ', 'BMZ', 'LMZ', 'PBEZ']
        strPercentage = ('000' + (str(treatmentPercentage)).replace(".", "-"))[-4:]
        strZones = 'zones' if randomWithinZones else 'nozones'

        # Dictionary holding all district details including rotations & weighting for zone-weighted method
        ## Dictionary format ['DISTRICT NAME'] = ['Region Name', [minYrsAPZ, minYrsBMZ, minYrsLMZ], [maxYrsAPZ, maxYrsBMZ, maxYrsLMZ], zoneWeighting]
        districtDictionary = {}
        districtDictionary['FAR SOUTH WEST']    = ['Barwon South West',   [5, 8, 15],   [8, 20, 50],    0.50]
        #districtDictionary['GOULBURN']          = ['Hume',                [4, 8, 15],   [8, 15, 50],    0.5]
        districtDictionary['LATROBE']           = ['Gippsland',           [4, 8, 15],   [8, 15, 50],    0.60]
        districtDictionary['MACALISTER']        = ['Gippsland',           [4, 8, 15],   [8, 15, 50],    0.60]
        districtDictionary['MALLEE']            = ['Loddon Mallee',       [5, 17, 15],  [12, 21, 50],   0.75]
        districtDictionary['METROPOLITAN']      = ['Port Phillip',        [5, 8, 15],   [8, 15, 50],    0.50]
        districtDictionary['MIDLANDS']          = ['Grampians',           [7, 12, 15],   [9, 14, 50],   0.75]
        districtDictionary['MURRAY GOLDFIELDS'] = ['Loddon Mallee',       [6, 12, 15],  [15, 30, 50],   0.50]
        #districtDictionary['MURRINDINDI']       = ['Hume',                [4, 8, 15],   [8, 15, 50],    0.5]
        districtDictionary['OTWAY']             = ['Barwon South West',   [5, 8, 15],   [8, 13, 50],    0.50]
        #districtDictionary['OVENS']             = ['Hume',                [4, 8, 15],   [8, 15, 50],    0.5]
        districtDictionary['SNOWY']             = ['Gippsland',           [4, 8, 15],   [8, 15, 50],    0.60]
        districtDictionary['TAMBO']             = ['Gippsland',           [4, 8, 15],   [8, 15, 50],    0.60]
        #districtDictionary['UPPER MURRAY']      = ['Hume',                [7, 12, 15],  [7, 12, 50],    0.5]
        districtDictionary['WIMMERA']           = ['Grampians',           [6, 12, 15],   [8, 14, 50],   0.90]
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
                arcpy.AddMessage(field_name + ' field exists in ' + str(shapefile))
                result = "exists"
            else:
                # Add a new field of that name   
                arcpy.AddField_management(shapefile, field_name, *args)
                arcpy.AddMessage(field_name + ' field missing from ' + str(shapefile) + '... adding')
                result = "added"
            return result

        # Function to create an empty copy of a shapefile
        def duplicate_empty_shapefile(input_shapefile, output_shapefile):
            # Create a list of fields including geometry
            lstFields = [field.name for field in arcpy.ListFields(input_shapefile) if field.type not in ['Geometry']]
            lstFields.append("SHAPE@") # add the full Geometry object

            # Copy the shapefile
            arcpy.CopyFeatures_management(input_shapefile, output_shapefile)

            # Delete all rows
            targetCursor = arcpy.da.UpdateCursor(output_shapefile, lstFields)
            for row in targetCursor:
                targetCursor.deleteRow()
            del targetCursor  

        # Function to turn Burn_Date into SEASON
        def burndate_to_season(burnDate):
            #arcpy.AddMessage('burnDate: ' + str(burnDate))
            year, month = int(str(burnDate)[0:4]), int(str(burnDate)[4:6])
            if month <= 6:
                return int(year)
            else:
                return int(year) + 1

        # Create a copy of the input shapefile so we're not doing any editing directly in the source file
        newburnunits = out_folder_path + '\\' + os.path.split(burnunits)[1]
        arcpy.CopyFeatures_management(burnunits, newburnunits)
        burnunits = newburnunits
        outputString = os.path.splitext(burnunits)[0] + '_' + strPercentage + 'pc_' + strZones + '_' + str(yearStart) + 'to' + str(yearFinish)

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
        del cursor

        # Create a CSV log file
        logfileName = (outputString + '_log.csv')
        logfile = open(os.path.join(out_folder_path, logfileName), 'w', newline='')
        writer = csv.writer(logfile)
        header =    ['district', 'region', 
                    'apz_total_ha', 'bmz_total_ha', 'lmz_total_ha', 'pbez_total_ha', 
                    'apz_min_rot', 'apz_max_rot', 'bmz_min_rot', 'bmz_max_rot', 
                    'zone_weighting', 'random_weighting', 
                    'apz_annual_ha', 'bmz_annual_ha', 'lmz_annual_ha', 
                    'apz_rot', 'bmz_rot', 'lmz_rot', 
                    'apz_prop', 'bmz_prop', 'lmz_prop'
                    ]
        writer.writerow(header)

        for replicate in range (1, replicates + 1):
                    
            arcpy.AddMessage("Processing replicate " + str(replicate))

            # Duplicate the burn units layer then empty it out (so we've got a shapefile to dump stuff in later)
            strReplicate = ('0' + str(replicate))[-2:]
            burnunits_output = outputString + '_r' + strReplicate +'.shp'
            
            duplicate_empty_shapefile(burnunits, burnunits_output)

            # # Make a copy of the empty burn units layer for the Phoenix fire history version
            # burnunits_output_phx = os.path.splitext(burnunits_output)[0] + '_phx.shp'
            # arcpy.CopyFeatures_management(burnunits_output, burnunits_output_phx)

            # Make a list of fields in the shapefile
            lstFields = [field.name for field in arcpy.ListFields(burnunits_output) if field.type not in ['Geometry']]
            lstFields.append("SHAPE@") # add the full Geometry object

            # populate sort field with random values
            with arcpy.da.UpdateCursor(burnunits, [sort_field]) as cursor:
                for row in cursor:
                    row[0] = random.random()
                    cursor.updateRow(row)
            del cursor
            
            # export a sorted copy (because the SQL sort in searchCursor only works in geodatabases apparently)
            burnunits_sorted = os.path.splitext(burnunits)[0] + '_sorted.shp'
            arcpy.Sort_management(burnunits , burnunits_sorted, [[sort_field, "ASCENDING"]])

            
            for district in districtDictionary.keys():
                region = districtDictionary.get(district)[0]
                
                # Create an expression with proper delimiters
                expression = arcpy.AddFieldDelimiters(burnunits, district_field) + " = '" + district + "'"
                
                selectedArea = [0, 0, 0, 0]      # [APZ, BMZ, LMZ, PBEZ] selected hectares

                # Calculate gross hectares per zone - I'm sure there's a more efficient way to do this but it works!
                with arcpy.da.SearchCursor(burnunits_sorted, [id_field, region_field, district_field, zone_field, grossarea_field], where_clause=expression) as cursor:
                    for row in cursor:
                        if row[3] == "APZ":
                            selectedArea[0] += row[4]
                        elif row[3] == "BMZ":
                            selectedArea[1] += row[4]
                        elif row[3] == "LMZ":
                            selectedArea[2] += row[4]
                        elif row[3] == "PBEZ":
                            selectedArea[3] += row[4]
                totalHectaresExPBEZ = sum(selectedArea) - selectedArea[3]

                # Determine the rotations and annual hectares required for each zone
                # Rotation is the number of years to divide the zone into, which is also the number of years between repeat treatments for each burn unit
                totalAnnualHectares = totalHectaresExPBEZ * (treatmentPercentage / 100)

                # Calculate requirements for random selection within districts. Also used to weight selection within zones.
                rand_apzAnnualHectares = (selectedArea[0] / totalHectaresExPBEZ) * totalAnnualHectares
                rand_apzRotation = math.trunc(selectedArea[0]/rand_apzAnnualHectares)
                rand_bmzAnnualHectares = (selectedArea[1] / totalHectaresExPBEZ) * totalAnnualHectares
                rand_bmzRotation = math.trunc(selectedArea[1]/rand_bmzAnnualHectares)
                rand_lmzAnnualHectares = (selectedArea[2] / totalHectaresExPBEZ) * totalAnnualHectares
                rand_lmzRotation = math.trunc(selectedArea[2]/rand_lmzAnnualHectares)
                rand_setAnnualHectares = [rand_apzAnnualHectares, rand_bmzAnnualHectares, rand_lmzAnnualHectares]
                rand_setRotation = [rand_apzRotation, rand_bmzRotation, rand_lmzRotation]

                # Calculate requirements for selection within zones
                ## Get the Min and Max rotations for current district
                minRotation = districtDictionary.get(district)[1]
                maxRotation = districtDictionary.get(district)[2]

                # Now turn these into hectares and proportions
                minHa = [(selectedArea[0] / maxRotation[0]), (selectedArea[1] / maxRotation[1]), (selectedArea[2]/maxRotation[2])]
                maxHa = [(selectedArea[0] / minRotation[0]), (selectedArea[1] / minRotation[1]), (selectedArea[2]/minRotation[2])]
                minHaApzBmz = minHa[0] + minHa[1]
                minHaApzBmzLmz = minHa[0] + minHa[1] + minHa[2]
                proportionMinHaApzBmz = [(minHa[0] / minHaApzBmz), (minHa[1] / minHaApzBmz)]
                proportionMinHaApzBmzLmz = [(minHa[0] / minHaApzBmzLmz), (minHa[1] / minHaApzBmzLmz), (minHa[2] / minHaApzBmzLmz)]
                proportionMaxHaApzBmzLmz = [(maxHa[0] / minHaApzBmzLmz), (maxHa[1] / minHaApzBmzLmz), (maxHa[2] / minHaApzBmzLmz)] # delete? I don't think this is used anywhere
                proportionRandomWithoutZones = [(rand_apzAnnualHectares / totalAnnualHectares), (rand_bmzAnnualHectares / totalAnnualHectares), (rand_lmzAnnualHectares / totalAnnualHectares)]

                if randomWithinZones == False:
                    # ignore zones and allocate hectares according to zone proportion
                    apzAnnualHectares = rand_apzAnnualHectares
                    apzRotation = rand_apzRotation
                    bmzAnnualHectares = rand_bmzAnnualHectares
                    bmzRotation = rand_bmzRotation
                    lmzAnnualHectares = rand_lmzAnnualHectares
                    lmzRotation = rand_lmzRotation
                    setAnnualHectares = rand_setAnnualHectares
                    setRotation = rand_setRotation
                    setProportion = [(apzAnnualHectares / totalAnnualHectares), (bmzAnnualHectares / totalAnnualHectares), (lmzAnnualHectares / totalAnnualHectares)]

                elif randomWithinZones == True:
                    # Is annual hectares < required to treat APZ & BMZ at minimum rotation?
                    if totalAnnualHectares <= minHaApzBmz:
                        apzHa = totalAnnualHectares * proportionMinHaApzBmz[0]
                        bmzHa = totalAnnualHectares * proportionMinHaApzBmz[1]
                        lmzHa = 0
                    else:
                        # APZ and BMZ can't be pushed past their minimum rotation (max ha), so hectares are proportionally allocated across all 3 zones until these limits are reached, then sent to LMZ
                        apzHa = min(maxHa[0], minHa[0] + (totalAnnualHectares - minHaApzBmz) * proportionMinHaApzBmzLmz[0])
                        bmzHa = min(maxHa[1], minHa[1] + (totalAnnualHectares - minHaApzBmz) * proportionMinHaApzBmzLmz[1])
                        lmzHa = totalAnnualHectares - (apzHa + bmzHa)
                        setProportionZones = [(apzHa / totalAnnualHectares), (bmzHa / totalAnnualHectares), (lmzHa / totalAnnualHectares)]
                    
                    # Now we weight these to produce something between full random within zones and random without zones
                    zonalWeighting = districtDictionary.get(district)[3]    # pulls zone weighting from table
                    setProportionWeighted =     [(proportionRandomWithoutZones[0] * (1 - zonalWeighting) + setProportionZones[0] * zonalWeighting), 
                                                (proportionRandomWithoutZones[1] * (1 - zonalWeighting) + setProportionZones[1] * zonalWeighting),
                                                (proportionRandomWithoutZones[2] * (1 - zonalWeighting) + setProportionZones[2] * zonalWeighting)]
                    tempTotal = setProportionWeighted[0] + setProportionWeighted[1] + setProportionWeighted[2]
                    setProportion = [setProportionWeighted[0] * tempTotal, setProportionWeighted[1] * tempTotal, setProportionWeighted[2] * tempTotal]

                    # Use these proportions to calculate annual hectare requirements & rotations
                    apzAnnualHectares = setProportion[0] * totalAnnualHectares
                    apzRotation = math.trunc(selectedArea[0]/apzAnnualHectares)
                    bmzAnnualHectares = setProportion[1] * totalAnnualHectares
                    bmzRotation = math.trunc(selectedArea[1]/bmzAnnualHectares)
                    lmzAnnualHectares = setProportion[2] * totalAnnualHectares
                    lmzRotation = math.trunc(selectedArea[2]/lmzAnnualHectares)
                    setAnnualHectares = [apzAnnualHectares, bmzAnnualHectares, lmzAnnualHectares]
                    setRotation = [apzRotation, bmzRotation, lmzRotation]
                
                # Send some information to the geoprocessing messages screen, but only do it once.
                if replicate == 1:
                    arcpy.AddMessage(   district + ", " + region + ": " \
                                        + str(int(apzAnnualHectares)) + "ha/yr APZ, " + str(int(bmzAnnualHectares)) + "ha/yr BMZ, "  + str(int(lmzAnnualHectares)) + "ha/yr LMZ, " \
                                        + "(Rotation: " + str(apzRotation) + "/" + str(bmzRotation) + "/" + str(lmzRotation) + "yrs, " \
                                        + str(round(setProportion[0]* 100, 1)) + "/" + str(round(setProportion[1] * 100, 1)) + "/" + str(round(setProportion[2] * 100, 1)) + "%)")

                    # Send same information to the logfile
                    row =   [district, region, 
                            round(selectedArea[0], 1), round(selectedArea[1], 1), round(selectedArea[2], 1), round(selectedArea[3], 1), 
                            districtDictionary.get(district)[1][0], districtDictionary.get(district)[2][0],
                            districtDictionary.get(district)[1][1], districtDictionary.get(district)[2][1],
                            districtDictionary.get(district)[3], 1 - districtDictionary.get(district)[3],
                            round(apzAnnualHectares,1), round(bmzAnnualHectares, 1), round(lmzAnnualHectares, 1), 
                            apzRotation, bmzRotation, lmzRotation, 
                            round(setProportion[0]* 100, 1), round(setProportion[1] * 100, 1), round(setProportion[2] * 100, 1)
                            ]
                    writer.writerow(row)

                for zone in ["APZ", "BMZ", "LMZ"]:
                    expression = arcpy.AddFieldDelimiters(burnunits_sorted, district_field) + " = '" + district + "' AND " + arcpy.AddFieldDelimiters(burnunits_sorted, zone_field) + " = '" + zone + "' ORDER BY " + arcpy.AddFieldDelimiters(burnunits_sorted, sort_field)

                    currentHa = 0
                    currentYear = 1
                    currentRotation = 1

                    if zone == "APZ":
                        zoneAnnualHectares = setAnnualHectares[0]
                        zoneRotation = setRotation[0]
                        zoneMinimumYears = minRotation[0]
                    elif zone == "BMZ":
                        zoneAnnualHectares = setAnnualHectares[1]
                        zoneRotation = setRotation[1]
                        zoneMinimumYears = minRotation[1]
                    elif zone == "LMZ":
                        zoneAnnualHectares = setAnnualHectares[2]
                        zoneRotation = setRotation[2]
                        zoneMinimumYears = minRotation[2]

                    with arcpy.da.InsertCursor(burnunits_output, lstFields) as outputCursor:
                        with arcpy.da.UpdateCursor(burnunits_sorted, lstFields, where_clause=expression) as cursor:
                            for rotation in range(int(zoneRotation)):
                                for row in cursor:
                                    # add gross burn unit are to currentHa
                                    # arcpy.AddMessage("row = " + str(row))
                                    currentHa += row[lstFields.index(grossarea_field)]

                                    # determine which rotation the burn unit is in
                                    currentRotation = math.floor(currentHa / zoneAnnualHectares) + 1

                                    # send a copy of this polygon to the output shapefile for each repeat
                                    currentYear = currentRotation - 1

                                    while currentYear <= yearsSeries:

                                        if row[lstFields.index(timesincefire_field)] >= zoneMinimumYears: # This removes in a rather crude way any burning below minimum rotation. The burn unit will still proceed to later repeats.

                                            # set burn date
                                            burnDate = (yearStart + currentYear) * 10000 + 401
                                            row[lstFields.index(burndate_field)] = burnDate

                                            # set season
                                            season = burndate_to_season(burnDate)
                                            row[lstFields.index(season_field)] = season

                                            cursor.updateRow(row) 
                                            
                                            # send burn unit to output
                                            fieldValues = []
                                            for field in row:
                                                fieldValues.append(field)
                                            outputCursor.insertRow(fieldValues)
                                        
                                        # go to next repeat
                                        currentYear += zoneRotation 

                    del cursor

            # Create a Phoenix-ready fire history (ie. lastburnt)
            # Sort replicate by burn unit ID and descending burn date - Using management.Sort instead of SQL sorting the cursor because it was causing failure.
            # burnunits_output_phx_sort = os.path.splitext(burnunits_output_phx)[0] + '_sort.shp'
            # expression = (str(id_field) + ' ASCENDING;' + str(burndate_field) + ' DESCENDING')

            # arcpy.management.Sort(burnunits_output, burnunits_output_phx_sort, expression, "UR")

            # # Copy highest dated (most recent burn) to Phoenix file
            # with arcpy.da.InsertCursor(burnunits_output_phx, lstFields) as outputCursor:
            #     with arcpy.da.SearchCursor(burnunits_output_phx_sort, lstFields) as cursor:
            #         previous_buid = "nil"
            #         for row in cursor:
            #             current_buid = row[lstFields.index(id_field)]
            #             if current_buid == previous_buid:
            #                 # we've already got the highest burn date for this burn unit so do nothing
            #                 previous_buid = current_buid
            #             else:
            #                 # send burn unit to output
            #                 fieldValues = []
            #                 for field in row:
            #                     fieldValues.append(field)
            #                 outputCursor.insertRow(fieldValues)
            #                 previous_buid = current_buid
            # del outputCursor
            # del cursor
            
            # # Delete phx temporary sort shapefile
            # delete_shapefile(out_folder_path, burnunits_output_phx_sort)

        # Incorporate past fire history -- Completely skips this bit if no fire history is provided
        if includeFireHistory == True: 

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
                    sourceValue = row[lstFields_fireHistory.index("Source")]
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
                        needs_update = true
                    if needs_update:
                        cursor.updateRow(row)
            del cursor

            # Merge shapefiles, retaining only FIRETYPE, Burn_Date and SEASON
            for replicate in range (1, replicates + 1):
                arcpy.AddMessage('Joining fire history to replicate ' + str(replicate))

                strReplicate = ('0' + str(replicate))[-2:]
                burnunits_output = outputString + '_r' + strReplicate +'.shp'
                #burnunits_output_phx = os.path.splitext(burnunits_output)[0] + '_phx.shp'

                # Map fields for merge
                field_mappings = arcpy.FieldMappings()
                for field in [burndate_field, firetype_field, season_field]:
                    field_map = arcpy.FieldMap()
                    field_map.addInputField(fireHistory, field) 
                    field_map.addInputField(burnunits_output, field)
                    field_mappings.addFieldMap(field_map)

                # do the merge
                for shapefile in [burnunits_output]: #for shapefile in [burnunits_output, burnunits_output_phx]:
                    arcpy.AddMessage('Converting to Phoenix data file. Warning: Slow')

                    trim = os.path.splitext(shapefile)[0]
                    merged_output = trim + '_merged.shp'
                    temp_raster = 'temp_raster'
                    temp_ascii = trim + '.ASC'
                    phoenix_output = trim + '.zip'
                    cell_size = 30
                    dateString = (str(yearFinish) + '06-30')

                    arcpy.Merge_management([fireHistory, burnunits_output], merged_output, field_mappings)

                    # Create raster and run Phoenix Data Converter
                    if runPhoenixDataConverter == True:
                        arcpy.PolygonToRaster_conversion(merged_output, burndate_field, temp_raster, 'MAXIMUM_AREA', burndate_field, cell_size)
                        arcpy.RasterToASCII_conversion(temp_raster, temp_ascii)

                        # Run Phoenix Data Converter
                        pdc_string = (phoenixDataConverterLoc + '\Phoenix Data Converter.exe "' + str(temp_ascii) + '" "' + str(phoenix_output) + '" ' + str(cell_size) + ' ' + str(dateString))
                        arcpy.AddMessage('Phoenix Data Converter: ' + pdc_string)
                        subprocess.call(pdc_string)

                    # Clean up unwanted files
                    #os.remove(temp_raster)
                    #os.remove(temp_ascii)

        # Delete the burnunits_sorted shapefile 
        delete_shapefile(out_folder_path, burnunits_sorted)

        # Close the logfile
        logfile.close()

        return
