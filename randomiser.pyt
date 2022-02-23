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
        burndate_field = 'Burn_Date'
        timesincefire_field = 'TSF'

        zones = ['APZ', 'BMZ', 'LMZ', 'PBEZ']

        # Dictionary holding all district details including rotations & weighting for zone-weighted method
        ## Dictionary format ['DISTRICT NAME'] = ['Region Name', [minYrsAPZ, minYrsBMZ, minYrsLMZ], [maxYrsAPZ, maxYrsBMZ, maxYrsLMZ], zoneWeighting]
        districtDictionary = {}
        districtDictionary['FAR SOUTH WEST']    = ['Barwon South West',   [4, 8, 15], [8, 15, 50], 0.0]
        districtDictionary['GOULBURN']          = ['Hume',                [4, 8, 15], [8, 15, 50], 0.5]
        districtDictionary['LATROBE']           = ['Gippsland',           [4, 8, 15], [8, 15, 50], 0.5]
        districtDictionary['MACALISTER']        = ['Gippsland',           [4, 8, 15], [8, 15, 50], 0.5]
        districtDictionary['MALLEE']            = ['Loddon Mallee',       [4, 8, 15], [8, 15, 50], 0.5]
        districtDictionary['METROPOLITAN']      = ['Port Phillip',        [4, 8, 15], [8, 15, 50], 0.5]
        districtDictionary['MIDLANDS']          = ['Grampians',           [4, 8, 15], [8, 15, 50], 0.5]
        districtDictionary['MURRAY GOLDFIELDS'] = ['Loddon Mallee',       [4, 8, 15], [8, 15, 50], 0.5]
        districtDictionary['MURRINDINDI']       = ['Hume',                [4, 8, 15], [8, 15, 50], 0.5]
        districtDictionary['OTWAY']             = ['Barwon South West',   [4, 8, 15], [8, 15, 50], 0.5]
        districtDictionary['OVENS']             = ['Hume',                [4, 8, 15], [8, 15, 50], 0.5]
        districtDictionary['SNOWY']             = ['Gippsland',           [4, 8, 15], [8, 15, 50], 0.65]
        districtDictionary['TAMBO']             = ['Gippsland',           [4, 8, 15], [8, 15, 50], 0.5]
        districtDictionary['UPPER MURRAY']      = ['Hume',                [4, 8, 15], [8, 15, 50], 0.5]
        districtDictionary['WIMMERA']           = ['Grampians',           [4, 8, 15], [8, 15, 50], 0.5]
        districtDictionary['YARRA']             = ['Port Phillip',        [4, 8, 15], [8, 15, 50], 0.5]
        
        # Function to delete all parts of a shapefile
        def delete_shapefile(directory, shapefile_name):
            # remove path from shapefile_name if required
            shapefile_name = str(os.path.split(shapefile_name[1]))
            
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
                arcpy.AddMessage(field_name + " field exists") 
            else:
                # Add a new field of that name   
                arcpy.AddField_management(shapefile, field_name, *args)
                arcpy.AddMessage(field_name + " field did not exist... but now it does!") 
        
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


        # Create a copy of the input shapefile so we're not doing any editing directly in the source file
        newburnunits = out_folder_path + '\\' + os.path.split(burnunits)[1]
        arcpy.CopyFeatures_management(burnunits, newburnunits)
        burnunits = newburnunits

        # Prepare the input shapefile
        add_field(burnunits, sort_field, "DOUBLE", 6, 4)
        add_field(burnunits, timesincefire_field, "LONG")
        add_field(burnunits, burndate_field, "LONG")
        add_field(burnunits, firetype_field, "STRING", 10)

        # populate FIRETYPE field (can't assume it's correct)
        with arcpy.da.UpdateCursor(burnunits, firetype_field) as cursor:
            for row in cursor:
                row[0] = "BURN"
                cursor.updateRow(row)
        del cursor

        for replicate in range (1, replicates + 1):
                    
            arcpy.AddMessage("Processing replicate " + str(replicate))

            # Duplicate the burn units layer then empty it out (so we've got a shapefile to dump stuff in later)
            tempStrPercentage = ("000" + (str(treatmentPercentage)).replace(".", "-"))
            tempStrReplicate = ("0" + str(replicate))
            if randomWithinZones == True:
                tempStrZones = "zones"
            else:
                tempStrZones = "nozones"
            burnunits_output = os.path.splitext(burnunits)[0] + "_" + tempStrPercentage[-4:] + "pc_" + tempStrZones + "_r" + tempStrReplicate[-2:] +'.shp'
            
            duplicate_empty_shapefile(burnunits, burnunits_output)
            lstFields = [field.name for field in arcpy.ListFields(burnunits_output) if field.type not in ['Geometry']]
            lstFields.append("SHAPE@") # add the full Geometry object

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

            
            for district in districtDictionary.keys():
                region = districtDictionary.get(district)[0]
                
                # Create an expression with proper delimiters
                expression = arcpy.AddFieldDelimiters(burnunits, district_field) + " = '" + district + "'"
                # arcpy.AddMessage(expression)
                
                zonearea = [0, 0, 0, 0, 0]      # [APZ, BMZ, LMZ, PBEZ] selected hectares

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
                minRotation = districtDictionary.get(district)[1]
                maxRotation = districtDictionary.get(district)[2]

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
                    zonalWeighting = districtDictionary.get(district)[3]    # pulls zone weighting from table
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
                    arcpy.AddMessage(   district + ", " + region + ": " \
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
            
            # Delete phx temporary sort shapefile
            delete_shapefile(out_folder_path, burnunits_output_phx_sort)

        # Create raster

        # Run Phoenix Data Converter

        # Clean up unwanted files

        # Delete the burnunits_sorted shapefile 
        delete_shapefile(out_folder_path, burnunits_sorted)

        return

# TO DO
# 4. Merge in pre-schedule fire history
# 5. Run Phoenix Data Converter to product Phoenix fire histories (be sure to check sort order is correct) - Or do we? This would require us to know which date should be used.
# 6. Create a log file (CSV maybe?) to hold the internal details such as rotation and hectares per zone that were used to create the fire histories