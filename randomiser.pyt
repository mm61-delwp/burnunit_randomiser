# -*- coding: utf-8 -*-

import arcpy, random, math, os, glob


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
        self.label = "Randomise burn unit treatment schedule"
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

        params = [param0, param1, param2, param3, param4, param5, param6]
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

        # Turn the tool parameters into usable variables
        burnunits = parameters[0].valueAsText
        out_folder_path = parameters[1].valueAsText 
        treatmentPercentage = float(parameters[2].valueAsText)
        replicates = int(parameters[3].valueAsText)
        yearStart = int(parameters[4].valueAsText)
        yearFinish = int(parameters[5].valueAsText)
        randomChecked = parameters[6].valueAsText
        if randomChecked == "true":
            randomWithinZones = True
        else:
            randomWithinZones = False
        yearsSeries = yearFinish - yearStart

        arcpy.AddMessage("burnunits = " + burnunits)
        arcpy.AddMessage("out_folder_path = " + out_folder_path)
        arcpy.AddMessage("treatmentPercentage = " + str(treatmentPercentage))
        arcpy.AddMessage("replicates = " + str(replicates))
        arcpy.AddMessage("randomWithinZones = " + str(randomWithinZones))

        # Define shapefile attributes
        id_field = 'BUID'
        region_field = 'DELWP_REGI'
        district_field = 'DISTRICT_N'
        zone_field = 'FireFMZ'
        grossarea_field = 'AreaHa'
        sort_field = 'sort'
        firetype_field = 'FIRETYPE'
        burndate_field = "Burn_Date"
        timesincefire_field = "TSF"

        # Set the minimum and maximum rotation for [APZ, BMZ, LMZ]
        ## Dictionary format ['DISTRICT NAME'] = [[minYrsAPZ, minYrsBMZ, minYrsLMZ], [maxYrsAPZ, maxYrsBMZ, maxYrsLMZ], zoneWeighting]
        minMaxRotationDistrictDict = {}
        minMaxRotationDistrictDict['FAR SOUTH WEST']    = [[4, 8, 15], [8, 15, 50], 0.0]
        minMaxRotationDistrictDict['GOULBURN']          = [[4, 8, 15], [8, 15, 50], 0.5]
        minMaxRotationDistrictDict['LATROBE']           = [[4, 8, 15], [8, 15, 50], 0.5]
        minMaxRotationDistrictDict['MACALISTER']        = [[4, 8, 15], [8, 15, 50], 0.5]
        minMaxRotationDistrictDict['MALLEE']            = [[4, 8, 15], [8, 15, 50], 0.5]
        minMaxRotationDistrictDict['METROPOLITAN']      = [[4, 8, 15], [8, 15, 50], 0.5]
        minMaxRotationDistrictDict['MIDLANDS']          = [[4, 8, 15], [8, 15, 50], 0.5]
        minMaxRotationDistrictDict['MURRAY GOLDFIELDS'] = [[4, 8, 15], [8, 15, 50], 0.5]
        minMaxRotationDistrictDict['MURRINDINDI']       = [[4, 8, 15], [8, 15, 50], 0.5]
        minMaxRotationDistrictDict['OTWAY']             = [[4, 8, 15], [8, 15, 50], 0.5]
        minMaxRotationDistrictDict['OVENS']             = [[4, 8, 15], [8, 15, 50], 0.5]
        minMaxRotationDistrictDict['SNOWY']             = [[4, 8, 15], [8, 15, 50], 0.65]
        minMaxRotationDistrictDict['TAMBO']             = [[4, 8, 15], [8, 15, 50], 0.5]
        minMaxRotationDistrictDict['UPPER MURRAY']      = [[4, 8, 15], [8, 15, 50], 0.5]
        minMaxRotationDistrictDict['WIMMERA']           = [[4, 8, 15], [8, 15, 50], 0.5]
        minMaxRotationDistrictDict['YARRA']             = [[4, 8, 15], [8, 15, 50], 0.5]
        
        # Set the proportion of zonal weighting between 1.0 (completely random within zones) and 0.0 (completely random, ignoring zones)
        zonalWeighting = 0.5

        # Just a list of regions & districts    ... Now that we have a dictionary (see above), probably should tidy things up so these aren't necessary.
        barwonsouthwest_districts = ['FAR SOUTH WEST', 'OTWAY']
        gippsland_districts =  ['SNOWY', 'TAMBO', 'MACALISTER', 'LATROBE']
        grampians_districts = ['WIMMERA', 'MIDLANDS']
        hume_districts = ['GOULBURN', 'MURRINDINDI', 'OVENS', 'UPPER MURRAY']
        loddonmallee_districts = ['MALLEE', 'MURRAY GOLDFIELDS']
        portphillip_districts = ['METROPOLITAN', 'YARRA']

        regions =   [
                    ["Barwon South West", barwonsouthwest_districts],
                    ["Gippsland", gippsland_districts],
                    ["Grampians", grampians_districts],
                    ["Hume", hume_districts],
                    ["Loddon Mallee", loddonmallee_districts],
                    ["Port Phillip", portphillip_districts]
                    ]

        zones = ['APZ', 'BMZ', 'LMZ', 'PBEZ']

        # Create a copy of the input shapefile so we're not doing any editing directly in the source file
        newburnunits = out_folder_path + '\\' + os.path.split(burnunits)[1]
        arcpy.CopyFeatures_management(burnunits, newburnunits)
        burnunits = newburnunits

        # Prepare the input shapefile
        try:
            # check if the sort field exists
            if arcpy.ListFields(burnunits, sort_field): #if field exists, evaluates to true
                arcpy.AddMessage("sort field exists") 
            else:
                # Add a new field of that name   
                arcpy.AddField_management(burnunits, sort_field, "DOUBLE", 6, 4)
                arcpy.AddMessage("sort field did not exist... but now it does!") 
        except Exception as e:
            arcpy.AddMessage(arcpy.GetMessages())

        try:
            # check if the time since fire field exists
            if arcpy.ListFields(burnunits, timesincefire_field): #if field exists, evaluates to true
                arcpy.AddMessage("time since fire field exists") 
            else:
                # Add a new field of that name   
                arcpy.AddField_management(burnunits, timesincefire_field, "LONG")
                arcpy.AddMessage("time since fire field did not exist... but now it does!") 
        except Exception as e:
            arcpy.AddMessage(arcpy.GetMessages())

        try:
            # check if the Burn_Date field exists
            if arcpy.ListFields(burnunits, burndate_field): #if field exists, evaluates to true
                arcpy.AddMessage("Burn_Date field exists") 
            else:
                # Add a new field of that name   
                arcpy.AddField_management(burnunits, burndate_field, "LONG")
                arcpy.AddMessage("Burn_Date field did not exist... but now it does!") 
        except Exception as e:
            arcpy.AddMessage(arcpy.GetMessages())

        try:
            # check if the FIRETYPE field exists
            if arcpy.ListFields(burnunits, firetype_field): #if field exists, evaluates to true
                arcpy.AddMessage("FIRETYPE field exists") 
            else:
                # Add a new field of that name   
                arcpy.AddField_management(burnunits, firetype_field, "STRING", 10)
                arcpy.AddMessage("FIRETYPE field did not exist... but now it does!") 
        except Exception as e:
            arcpy.AddMessage(arcpy.GetMessages())

        # populate FIRETYPE field (can't assume it's correct)
        with arcpy.da.UpdateCursor(burnunits, firetype_field) as cursor:
            for row in cursor:
                row[0] = "BURN"
                cursor.updateRow(row)
        del cursor

        for replicate in range (1, replicates + 1):
                    
            arcpy.AddMessage("Processing replicate " + str(replicate))
            
            # Duplicate the burn units layer then empty it out (so we've got a shapefile to dump stuff in later)
            lstFields = [field.name for field in arcpy.ListFields(burnunits) if field.type not in ['Geometry']]
            lstFields.append("SHAPE@") # add the full Geometry object
            tempStrPercentage = ("000" + (str(treatmentPercentage)).replace(".", "-"))
            tempStrReplicate = ("0" + str(replicate))
            if randomWithinZones == True:
                tempStrZones = "zones"
            else:
                tempStrZones = "nozones"
            burnunits_output = os.path.splitext(burnunits)[0] + "_" + tempStrPercentage[-4:] + "pc_" + tempStrZones + "_r" + tempStrReplicate[-2:] +'.shp'
            arcpy.CopyFeatures_management(burnunits, burnunits_output)
            targetCursor = arcpy.da.UpdateCursor(burnunits_output, lstFields)
            for row in targetCursor:
                targetCursor.deleteRow()
            del targetCursor

            # Duplicate the empty burn units layer for the Phoenix fire history version
            burnunits_output_phx = os.path.splitext(burnunits)[0] + "_" + tempStrPercentage[-4:] + "pc_" + tempStrZones + "_r" + tempStrReplicate[-2:] +'_phx.shp'
            arcpy.CopyFeatures_management(burnunits_output, burnunits_output_phx)
            
            # populate sort field with random values
            with arcpy.da.UpdateCursor(burnunits, ["sort"]) as cursor:
                for row in cursor:
                    row[0] = random.random()
                    cursor.updateRow(row)
            del cursor
            
            # export a sorted copy (because the SQL sort in searchCursor only works in geodatabases apparently)
            burnunits_sorted = os.path.splitext(burnunits)[0] + '_sorted.shp'
            arcpy.Sort_management(burnunits , burnunits_sorted, [["sort", "ASCENDING"]]) # replace "sort" with sort_field

            for region in regions:
                for district in region[1]:
                    
                    # Create an expression with proper delimiters
                    expression = arcpy.AddFieldDelimiters(burnunits, district_field) + " = '" + district + "'"
                    # arcpy.AddMessage(expression)
                    
                    zonearea = [0, 0, 0, 0, 0]      # [APZ, BMZ, LMZ, PBEZ] hectares

                    # Calculate gross hectares per zone - I'm sure there's a more efficient way to do this but it works!
                    with arcpy.da.SearchCursor(burnunits_sorted, [id_field, region_field, district_field, zone_field, grossarea_field], where_clause=expression) as cursor:
                        for row in cursor:
                            if row[3] == "APZ":
                                zonearea[0] += row[4]
                            elif row[3] == "BMZ":
                                zonearea[1] += row[4]
                            elif row[3] == "LMZ":
                                zonearea[2] += row[4]
                            elif row[3] == "PBEZ":
                                zonearea[3] += row[4]
                    totalHectares = sum(zonearea)
                    totalHectaresExPBEZ = sum(zonearea) - zonearea[3]

                    # Determine the rotations and annual hectares required for each zone
                    # Rotation is the number of years to divide the zone into, which is also the number of years between repeat treatments for each burn unit
                    totalAnnualHectares = totalHectaresExPBEZ * (treatmentPercentage / 100)

                    # Calculate requirements for random selection within districts. Also used to weight selection within zones.
                    rand_apzAnnualHectares = (zonearea[0] / totalHectaresExPBEZ) * totalAnnualHectares
                    rand_apzRotation = math.trunc(zonearea[0]/rand_apzAnnualHectares)
                    rand_bmzAnnualHectares = (zonearea[1] / totalHectaresExPBEZ) * totalAnnualHectares
                    rand_bmzRotation = math.trunc(zonearea[1]/rand_bmzAnnualHectares)
                    rand_lmzAnnualHectares = (zonearea[2] / totalHectaresExPBEZ) * totalAnnualHectares
                    rand_lmzRotation = math.trunc(zonearea[2]/rand_lmzAnnualHectares)
                    rand_setAnnualHectares = [rand_apzAnnualHectares, rand_bmzAnnualHectares, rand_lmzAnnualHectares]
                    rand_setRotation = [rand_apzRotation, rand_bmzRotation, rand_lmzRotation]

                    # Calculate requirements for selection within zones
                    ## Get the Min and Max rotations for current district
                    minRotation = minMaxRotationDistrictDict.get(district)[0]
                    maxRotation = minMaxRotationDistrictDict.get(district)[1]

                    # Now turn these into hectares and proportions
                    minHa = [(zonearea[0] / maxRotation[0]), (zonearea[1] / maxRotation[1]), (zonearea[2]/maxRotation[2])]
                    maxHa = [(zonearea[0] / minRotation[0]), (zonearea[1] / minRotation[1]), (zonearea[2]/minRotation[2])]
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
                        zonalWeighting = minMaxRotationDistrictDict.get(district)[2]    # pulls zone weighting from table
                        setProportionWeighted =     [(proportionRandomWithoutZones[0] * (1 - zonalWeighting) + setProportionZones[0] * zonalWeighting), 
                                                    (proportionRandomWithoutZones[1] * (1 - zonalWeighting) + setProportionZones[1] * zonalWeighting),
                                                    (proportionRandomWithoutZones[2] * (1 - zonalWeighting) + setProportionZones[2] * zonalWeighting)]
                        tempTotal = setProportionWeighted[0] + setProportionWeighted[1] + setProportionWeighted[2]
                        setProportion = [setProportionWeighted[0] * tempTotal, setProportionWeighted[1] * tempTotal, setProportionWeighted[2] * tempTotal]

                        # Use these proportions to calculate annual hectare requirements & rotations
                        apzAnnualHectares = setProportion[0] * totalAnnualHectares
                        apzRotation = math.trunc(zonearea[0]/apzAnnualHectares)
                        bmzAnnualHectares = setProportion[1] * totalAnnualHectares
                        bmzRotation = math.trunc(zonearea[1]/bmzAnnualHectares)
                        lmzAnnualHectares = setProportion[2] * totalAnnualHectares
                        lmzRotation = math.trunc(zonearea[2]/lmzAnnualHectares)
                        setAnnualHectares = [apzAnnualHectares, bmzAnnualHectares, lmzAnnualHectares]
                        setRotation = [apzRotation, bmzRotation, lmzRotation]
                    
                    # Send some information to the geoprocessing messages screen, but only do it once.
                    if replicate == 1:
                        arcpy.AddMessage(   region[0] + ", " + district + ": " \
                                            + str(int(apzAnnualHectares)) + "ha/yr APZ, " + str(int(bmzAnnualHectares)) + "ha/yr BMZ, "  + str(int(lmzAnnualHectares)) + "ha/yr LMZ, " \
                                            + "(Rotation: " + str(apzRotation) + "/" + str(bmzRotation) + "/" + str(lmzRotation) + "yrs, " \
                                            + str(round(setProportion[0]* 100, 1)) + "/" + str(round(setProportion[1] * 100, 1)) + "/" + str(round(setProportion[2] * 100, 1)) + "%)")

                    for zone in ["APZ", "BMZ", "LMZ"]:
                        expression = arcpy.AddFieldDelimiters(burnunits_sorted, district_field) + " = '" + district + "' AND " + arcpy.AddFieldDelimiters(burnunits_sorted, zone_field) + " = '" + zone + "' ORDER BY " + arcpy.AddFieldDelimiters(burnunits_sorted, "sort")

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
                                                row[lstFields.index("Burn_Date")] = burnDate
                                                cursor.updateRow(row) 
                                                
                                                # send burn unit to output
                                                fieldValues = []
                                                for field in row:
                                                    fieldValues.append(field)
                                                outputCursor.insertRow(fieldValues)
                                            
                                            # go to next repeat
                                            currentYear += zoneRotation 
            # Incorporate past fire history

            # Create a Phoenix-ready fire history (ie. lastburnt)
            # Sort replicate by burn unit ID and descending burn date - Using management.Sort instead of SQL sorting the cursor because it was causing failure.
            burnunits_output_phx_sort = os.path.splitext(burnunits_output_phx)[0] + '_sort.shp'
            arcpy.management.Sort(burnunits_output, burnunits_output_phx_sort, "BUID ASCENDING;Burn_Date DESCENDING", "UR")
            with arcpy.da.InsertCursor(burnunits_output_phx, lstFields) as outputCursor:
                with arcpy.da.SearchCursor(burnunits_output_phx_sort, lstFields) as cursor:
                    previous_buid = "nil"
                    for row in cursor:
                        current_buid = row[lstFields.index(id_field)]
                        if current_buid == previous_buid:
                            # we've already got the highest burn date for this burn unit so do nothing
                            previous_buid = current_buid
                        else:
                            # send burn unit to output
                            fieldValues = []
                            for field in row:
                                fieldValues.append(field)
                            outputCursor.insertRow(fieldValues)
                            previous_buid = current_buid
            
            # Delete temporary sort shapefile
            files = glob.glob(os.path.splitext(burnunits_output_phx_sort)[0] + '.*')
            for file in files:
                os.remove(file)

        # Create raster

        # Run Phoenix Data Converter

        # Clean up unwanted files

        # Get all files of burnunits_sorted shapefile and then delete them
        files = glob.glob(os.path.splitext(burnunits_sorted)[0] + '.*')
        for file in files:
            os.remove(file)

        return

# TO DO
# 4. Merge in pre-schedule fire history
# 5. Run Phoenix Data Converter to product Phoenix fire histories (be sure to check sort order is correct) - Or do we? This would require us to know which date should be used.
# 6. Create a log file (CSV maybe?) to hold the internal details such as rotation and hectares per zone that were used to create the fire histories