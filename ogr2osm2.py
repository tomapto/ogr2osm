#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" ogr2osm beta

This program takes any vector data understadable by OGR and outputs an OSM file
with that data.

By default tags will be naively copied from the input data. Hooks are provided
so that, with a little python programming, you can translate the tags however
you like. More hooks are provided so you can filter or even modify the features
themselves.

To use the hooks, create a file in the translations/ directory called myfile.py
and run ogr2osm.py -t myfile. This file should define a function with the name
of each hook you want to use. For an example, see the uvmtrans.py file.

The program will use projection metadata from the source, if it has any. If
there is no projection information, or if you want to override it, you can use
-e or -p to specify an EPSG code or Proj.4 string, respectively. If there is no
projection metadata and you do not specify one, EPSG:4326 will be used (WGS84
latitude-longitude)

For additional usage information, run ogr2osm.py --help



Copyright (c) 2012 The University of Vermont
<andrew.guertin@uvm.edu
Released under the MIT license: http://opensource.org/licenses/mit-license.php

Based very heavily on code released under the following terms:

(c) Iván Sánchez Ortega, 2009
<ivan@sanchezortega.es>
###############################################################################
#  "THE BEER-WARE LICENSE":                                                   #
#  <ivan@sanchezortega.es> wrote this file. As long as you retain this notice #
#  you can do whatever you want with this stuff. If we meet some day, and you #
#  think this stuff is worth it, you can buy me a beer in return.             #
###############################################################################

"""

import sys
import os
from optparse import OptionParser
import logging as l

l.basicConfig(level=l.DEBUG, format="%(message)s")

from osgeo import ogr
from osgeo import osr

from SimpleXMLWriter import XMLWriter

# Setup program usage
usage = "usage: %prog SRCFILE"
parser = OptionParser(usage=usage)
parser.add_option("-t", "--translation", dest="translationMethod",
                  metavar="TRANSLATION",
                  help="Select the attribute-tags translation method. See " +
                       "the translations/ directory for valid values.")
parser.add_option("-o", "--output", dest="outputFile", metavar="OUTPUT",
                  help="Set destination .osm file name and location.")
parser.add_option("-e", "--epsg", dest="sourceEPSG", metavar="EPSG_CODE",
                  help="EPSG code of source file. Do not include the " +
                       "'EPSG:' prefix. If specified, overrides projection " +
                       "from source metadata if it exists.")
parser.add_option("-p", "--proj4", dest="sourcePROJ4", metavar="PROJ4_STRING",
                  help="PROJ.4 string. If specified, overrides projection " +
                       "from source metadata if it exists.")
parser.add_option("-v", "--verbose", dest="verbose", action="store_true")
parser.add_option("-d", "--debug-tags", dest="debugTags", action="store_true",
                  help="Output the tags for every feature parsed.")
parser.add_option("-f", "--force", dest="forceOverwrite", action="store_true",
                  help="Force overwrite of output file.")

parser.set_defaults(sourceEPSG=None, sourcePROJ4=None, verbose=False,
                    debugTags=False,
                    translationMethod=None, outputFile=None,
                    forceOverwrite=False)

# Parse and process arguments
(options, args) = parser.parse_args()

try:
    if options.sourceEPSG:
        options.sourceEPSG = int(options.sourceEPSG)
except:
    parser.error("EPSG code must be numeric (e.g. '4326', not 'epsg:4326')")

if len(args) < 3:
    parser.print_help()
    parser.error("you must specify a source filename")
elif len(args) > 3:
    parser.error("you have specified too many arguments, " +
                 "only supply the source filename")

# Input and output file
# if no output file given, use the basename of the source but with .osm
sourceFile = os.path.realpath(args[0])
sourceFile1 = os.path.realpath(args[1])
sourceFile2 = os.path.realpath(args[2])

if options.outputFile is not None:
    options.outputFile = os.path.realpath(options.outputFile)
else:
    (base, ext) = os.path.splitext(os.path.basename(sourceFile))
    options.outputFile = os.path.join(os.getcwd(), base + ".osm")
if not options.forceOverwrite and os.path.exists(options.outputFile):
    parser.error("ERROR: output file '%s' exists" % (options.outputFile))
l.info("Preparing to convert file '%s' to '%s'." % (sourceFile, options.outputFile))

# Projection
if not options.sourcePROJ4 and not options.sourceEPSG:
    l.info("Will try to detect projection from source metadata, or fall back to EPSG:4326")
elif options.sourcePROJ4:
    l.info("Will use the PROJ.4 string: " + options.sourcePROJ4)
elif options.sourceEPSG:
    l.info("Will use EPSG:" + str(options.sourceEPSG))

# Stuff needed for locating translation methods
if options.translationMethod:
    # add dirs to path if necessary
    (root, ext) = os.path.splitext(options.translationMethod)
    if os.path.exists(options.translationMethod) and ext == '.py':
        # user supplied translation file directly
        sys.path.insert(0, os.path.dirname(root))
    else:
        # first check translations in the subdir translations of cwd
        sys.path.insert(0, os.path.join(os.getcwd(), "translations"))
        # then check subdir of script dir
        sys.path.insert(1, os.path.join(os.path.abspath(__file__), "translations"))
        # (the cwd will also be checked implicityly)

    # strip .py if present, as import wants just the module name
    if ext == '.py':
        options.translationMethod = os.path.basename(root)

    try:
        translations = __import__(options.translationMethod)
    except:
        parser.error("Could not load translation method '%s'. Translation "
                     "script must be in your current directory, or in the "
                     "translations/ subdirectory of your current or ogr2osm.py "
                     "directory.") % (options.translationMethod)
    l.info("Successfully loaded '%s' translation method ('%s')."
           % (options.translationMethod, os.path.realpath(translations.__file__)))
else:
    import types

    translations = types.ModuleType("translationmodule")
    l.info("Using default translations")

try:
    translations.filterLayer(None)
    l.debug("Using user filterLayer")
except:
    l.debug("Using default filterLayer")
    translations.filterLayer = lambda layer: layer

try:
    translations.filterFeature(None, None, None)
    l.debug("Using user filterFeature")
except:
    l.debug("Using default filterFeature")
    translations.filterFeature = lambda feature, fieldNames, reproject: feature

try:
    translations.filterTags(None)
    l.debug("Using user filterTags")
except:
    l.debug("Using default filterTags")
    translations.filterTags = lambda tags: tags

try:
    translations.filterFeaturePost(None, None, None)
    l.debug("Using user filterFeaturePost")
except:
    l.debug("Using default filterFeaturePost")
    translations.filterFeaturePost = lambda feature, fieldNames, reproject: feature

try:
    translations.preOutputTransform(None, None)
    l.debug("Using user preOutputTransform")
except:
    l.debug("Using default preOutputTransform")
    translations.preOutputTransform = lambda geometries, features: None

# Done options parsing, now to program code

# Some global variables to hold stuff...
geometries = []
features = []

zpoints = {}
# Helper function to get a new ID
elementIdCounter = 0

layer1 = ogr.Open("./hljsrc/R_LNameheilongjiang.dbf", 0).GetLayer()
layer2 = ogr.Open("./hljsrc/R_Nameheilongjiang.dbf", 0).GetLayer()

def getNewID():
    global elementIdCounter
    elementIdCounter -= 1
    return elementIdCounter


# Classes
class Geometry(object):
    id = 0

    def __init__(self):
        self.id = getNewID()
        self.parents = set()
        global geometries
        geometries.append(self)

    def replacejwithi(self, i, j):
        pass

    def addparent(self, parent):
        self.parents.add(parent)

    def removeparent(self, parent, shoulddestroy=True):
        self.parents.discard(parent)
        if shoulddestroy and len(self.parents) == 0:
            global geometries
            geometries.remove(self)


class Point(Geometry):
    def __init__(self, x, y,z):
        Geometry.__init__(self)
        self.x = x
        self.y = y
        self.z = z

    def replacejwithi(self, i, j):
        pass


class Way(Geometry):
    def __init__(self):
        Geometry.__init__(self)
        self.points = []

    def replacejwithi(self, i, j):
        self.points = map(lambda x: i if x == j else x, self.points)
        j.removeparent(self)
        i.addparent(self)


class Relation(Geometry):
    def __init__(self):
        Geometry.__init__(self)
        self.members = []

    def replacejwithi(self, i, j):
        self.members = map(lambda x: i if x == j else x, self.members)
        j.removeparent(self)
        i.addparent(self)


class Feature(object):
    geometry = None
    tags = {}

    def __init__(self):
        global features
        features.append(self)

    def replacejwithi(self, i, j):
        if self.geometry == j:
            self.geometry = i
        j.removeparent(self)
        i.addparent(self)


def getzPoint():
    dataSource1 = ogr.Open('hljsrc/Nhlj2.shp', 0)
    layer1 = dataSource1.GetLayer()
    lids = {}
    jj = 0
    for i in range(layer1.GetFeatureCount()):
        ogrfeature1 = layer1.GetNextFeature()
        if ogrfeature1 is None:
            continue

        lid1 = ogrfeature1.GetFieldAsString("Node_LID");
        if lid1 == '':
            continue
        ogrgeometry1 = ogrfeature1.GetGeometryRef()
        geometryType1 = ogrgeometry1.GetGeometryType()

        if (geometryType1 == ogr.wkbPoint or
                    geometryType1 == ogr.wkbPoint25D):
            x1 = ogrgeometry1.GetX()
            y1 = ogrgeometry1.GetY()
            lids[lid1] = (x1,y1)
    dataSource = ogr.Open('hljsrc/z_hlj2.shp', 0)
    layer = dataSource.GetLayer()

    for i in range(layer.GetFeatureCount()):
        ogrfeature = layer.GetNextFeature()
        z = ogrfeature.GetFieldAsString("Z");
        if z == '1':
            id = ogrfeature.GetFieldAsString("ID");
            snum = ogrfeature.GetFieldAsString("Seq_Nm");
            zpoints[jj] = id + "|" + snum
            jj +=1

            ogrgeometry = ogrfeature.GetGeometryRef()
            geometryType = ogrgeometry.GetGeometryType()

            if (geometryType == ogr.wkbPoint or
                        geometryType == ogr.wkbPoint25D):
                x = ogrgeometry.GetX()
                y = ogrgeometry.GetY()

            for (a, b) in lids.items():
                ids = a.split("|");
                if b == (x,y) and ids[0] == id:
                    zpoints[jj] = ids[1]+'|0'
                    jj += 1

                elif b == (x,y) and ids[1] == id:
                    zpoints[jj] = ids[1]+'|-1'
                    jj += 1
    return zpoints

def getFileData(filename,filename1,filename2):
    if not os.path.isfile(filename):
        parser.error("the file '%s' does not exist" % (filename))

    ''' 打开3个文件 R  R_LName R_Name'''
    dataSource = ogr.Open(filename, 0)  # 0 means read-only
    dataSource1 = ogr.Open(filename1, 0)  # 0 means read-only
    dataSource2 = ogr.Open(filename2, 0)  # 0 means read-only

    if dataSource is None:
        l.error('OGR failed to open ' + filename + ', format may be unsuported')
        sys.exit(1)
    return dataSource,dataSource1,dataSource2


def parseData(dataSource,dataSource1,dataSource2):
    l.debug("Parsing data")
    getzPoint()
    global translations
    for i in range(dataSource.GetLayerCount()):
        layer = dataSource.GetLayer(i)
        layer.ResetReading()
        parseLayer(translations.filterLayer(layer),dataSource1,dataSource2)


def getTransform(layer):
    global options
    # First check if the user supplied a projection, then check the layer,
    # then fall back to a default
    spatialRef = None
    if options.sourcePROJ4:
        spatialRef = osr.SpatialReference()
        spatialRef.ImportFromProj4(options.sourcePROJ4)
    elif options.sourceEPSG:
        spatialRef = osr.SpatialReference()
        spatialRef.ImportFromEPSG(options.sourceEPSG)
    else:
        spatialRef = layer.GetSpatialRef()
        if spatialRef != None:
            l.info("Detected projection metadata:\n" + str(spatialRef))
        else:
            l.info("No projection metadata, falling back to EPSG:4326")

    if spatialRef == None:
        # No source proj specified yet? Then default to do no reprojection.
        # Some python magic: skip reprojection altogether by using a dummy
        # lamdba funcion. Otherwise, the lambda will be a call to the OGR
        # reprojection stuff.
        reproject = lambda (geometry): None
    else:
        destSpatialRef = osr.SpatialReference()
        # Destionation projection will *always* be EPSG:4326, WGS84 lat-lon
        destSpatialRef.ImportFromEPSG(4326)
        coordTrans = osr.CoordinateTransformation(spatialRef, destSpatialRef)
        reproject = lambda (geometry): geometry.Transform(coordTrans)

    return reproject


def getLayerFields(layer):
    featureDefinition = layer.GetLayerDefn()
    fieldNames = []
    fieldCount = featureDefinition.GetFieldCount()
    for j in range(fieldCount):
        fieldNames.append(featureDefinition.GetFieldDefn(j).GetNameRef())
    return fieldNames

def getFeatureTags(ogrfeature, fieldNames,dataSource1,dataSource2):
    tags = {}
    strID = ogrfeature.GetFieldAsString("ID");
    strDirection = ogrfeature.GetFieldAsString("Direction");
    if strDirection == '0' or strDirection == '1':
        tags['oneway'] = 'no'
        tags['rDirection'] = 'no'
    elif strDirection == '2':
        tags['oneway'] = 'yes'
        tags['rDirection'] = 'no'
    elif strDirection == '3':
        tags['oneway'] = 'yes'
        tags['rDirection'] = 'yes'
    else:
        tags['oneway'] = 'no'
        tags['rDirection'] = 'no'

    '''
    layer1 = dataSource1.GetLayer()
    layer2 = dataSource2.GetLayer()
    layer1.SetAttributeFilter("ID = '"+ strID + "'" );

    strRouteID = "";
    for feature in layer1:
        strRouteID = feature.GetFieldAsString("Route_ID");

    if strRouteID != "":
        layer2.SetAttributeFilter("Route_ID = '"+ strRouteID + "'" + "and Language = '1'")
        for feature in layer2:
            tags['name'] = unicode(feature.GetFieldAsString("PathName"),'gbk')
    '''
    tags['name'] = u'河西路'
    tags['id'] = strID
    strKind = ogrfeature.GetFieldAsString("Kind").split("|")[0][0:2]
    strKind2 = ogrfeature.GetFieldAsString("Kind").split("|")[0][2:4]

    if strKind == "00" or strKind == '01':
        tags['highway'] ="motorway"
    elif strKind == "02":
        tags['highway'] = "trunk"
        if strKind2 == "0b":
            tags['highway'] = "trunk_link"
    elif strKind == "03":
        tags['highway'] = "primary"
        if strKind2 == "0b":
            tags['highway'] = "primary_link"
    elif strKind == "04":
        tags['highway'] = "secondary"
    elif strKind == "05":
        tags['highway'] = "tertiary"
    elif strKind == "06":
        tags['highway'] = "unclassified"
    elif strKind == "08":
        tags['highway'] = "residential"
    elif strKind == "0a":
        tags['highway'] = "living_street"
    elif strKind == "0b":
        tags['highway'] = "service"

    return translations.filterTags(tags)


def parseLayer(layer,dataSource1,dataSource2):
    if layer is None:
        return
    fieldNames = getLayerFields(layer)
    reproject = getTransform(layer)

    for j in range(layer.GetFeatureCount()):
        ogrfeature = layer.GetNextFeature()
        parseFeature(translations.filterFeature(ogrfeature, fieldNames, reproject), fieldNames, reproject,dataSource1,dataSource2)


def parseFeature(ogrfeature, fieldNames, reproject,dataSource1,dataSource2):
    if ogrfeature is None:
        return

    ogrgeometry = ogrfeature.GetGeometryRef()
    if ogrgeometry is None:
        return
    reproject(ogrgeometry)
    geometry = parseGeometry(ogrfeature,ogrgeometry)
    if geometry is None:
        return

    feature = Feature()
    feature.geometry = geometry
    feature.tags = getFeatureTags(ogrfeature, fieldNames,dataSource1,dataSource2)
    geometry.addparent(feature)

    translations.filterFeaturePost(feature, ogrfeature, ogrgeometry)


def parseGeometry(ogrfeature, ogrgeometry):
    geometryType = ogrgeometry.GetGeometryType()

    if (geometryType == ogr.wkbPoint or
                geometryType == ogr.wkbPoint25D):
        return parsePoint(ogrgeometry)
    elif (geometryType == ogr.wkbLineString or
                  geometryType == ogr.wkbLinearRing or
                  geometryType == ogr.wkbLineString25D):
        #         geometryType == ogr.wkbLinearRing25D does not exist
        return parseLineString(ogrfeature,ogrgeometry)
    elif (geometryType == ogr.wkbPolygon or
                  geometryType == ogr.wkbPolygon25D):
        return parsePolygon(ogrgeometry)
    elif (geometryType == ogr.wkbMultiPoint or
                  geometryType == ogr.wkbMultiLineString or
                  geometryType == ogr.wkbMultiPolygon or
                  geometryType == ogr.wkbGeometryCollection or
                  geometryType == ogr.wkbMultiPoint25D or
                  geometryType == ogr.wkbMultiLineString25D or
                  geometryType == ogr.wkbMultiPolygon25D or
                  geometryType == ogr.wkbGeometryCollection25D):
        return parseCollection(ogrfeature,ogrgeometry)
    else:
        l.warning("unhandled geometry, type: " + str(geometryType))
        return None


def parsePoint(ogrgeometry):
    x = ogrgeometry.GetX()
    y = ogrgeometry.GetY()
    geometry = Point(x, y,0)
    return geometry


def parseLineString(ogrfeature,ogrgeometry):
    geometry = Way()
    # LineString.GetPoint() returns a tuple, so we can't call parsePoint on it
    # and instead have to create the point ourself
    # 增加一个z-index
    strID = ogrfeature.GetFieldAsString("ID");

    for i in range(ogrgeometry.GetPointCount()):
        (x, y, unused) = ogrgeometry.GetPoint(i)

        mypoint = Point(x, y, 0)
        for (a,b) in zpoints.items():
            ids = b.split("|");
            if strID == ids[0] and str(i) == ids[1]:
                mypoint = Point(x, y,1)
            elif strID == ids[0] and ids[1] =='-1' and str(i) == ogrgeometry.GetPointCount()-1:
                mypoint = Point(x, y, 1)
        geometry.points.append(mypoint)
        mypoint.addparent(geometry)
    return geometry


def parsePolygon(ogrgeometry):
    # Special case polygons with only one ring. This does not (or at least
    # should not) change behavior when simplify relations is turned on.
    if ogrgeometry.GetGeometryCount() == 0:
        l.warning("Polygon with no rings?")
    elif ogrgeometry.GetGeometryCount() == 1:
        return parseLineString(ogrgeometry.GetGeometryRef(0))
    else:
        print "parsePolygon"
        geometry = Relation()
        try:
            exterior = parseLineString(ogrgeometry.GetGeometryRef(0))
            exterior.addparent(geometry)
        except:
            l.warning("Polygon with no exterior ring?")
            return None
        geometry.members.append((exterior, "outer"))
        for i in range(1, ogrgeometry.GetGeometryCount()):
            interior = parseLineString(ogrgeometry.GetGeometryRef(i))
            interior.addparent(geometry)
            geometry.members.append((interior, "inner"))
        return geometry


def parseCollection(ogrfeature,ogrgeometry):
    # OGR MultiPolygon maps easily to osm multipolygon, so special case it
    # TODO: Does anything else need special casing?
    geometryType = ogrgeometry.GetGeometryType()
    if (geometryType == ogr.wkbMultiPolygon or
                geometryType == ogr.wkbMultiPolygon25D):

        geometry = Relation()
        for polygon in range(ogrgeometry.GetGeometryCount()):
            exterior = parseLineString(ogrgeometry.GetGeometryRef(polygon).GetGeometryRef(0))
            exterior.addparent(geometry)
            geometry.members.append((exterior, "outer"))
            for i in range(1, ogrgeometry.GetGeometryRef(polygon).GetGeometryCount()):
                interior = parseLineString(ogrgeometry.GetGeometryRef(polygon).GetGeometryRef(i))
                interior.addparent(geometry)
                geometry.members.append((interior, "inner"))
    else:
        geometry = Way()

        strID = ogrfeature.GetFieldAsString("ID");
        nCount = 0
        for j in range(ogrgeometry.GetGeometryCount()):
            for i in range(ogrgeometry.GetGeometryRef(j).GetPointCount()):
                ogrgeometry2 = ogrgeometry.GetGeometryRef(j)
                if j<>0 and i ==0:
                    continue

                (x, y, unused) = ogrgeometry2.GetPoint(i)

                mypoint = Point(x, y, 0)
                for (a, b) in zpoints.items():
                    ids = b.split("|");
                    if strID == ids[0] and str(nCount) == ids[1]:
                        mypoint = Point(x, y, 1)
                geometry.points.append(mypoint)
                mypoint.addparent(geometry)
                nCount += 1
        return geometry

def mergePoints():
    l.debug("Merging points")
    global geometries
    points = [geometry for geometry in geometries if type(geometry) == Point]

    # Make list of Points at each location
    l.debug("Making list")
    pointcoords = {}
    for i in points:
        try:
            pointcoords[(i.x, i.y,i.z)].append(i)
        except KeyError:
            pointcoords[(i.x, i.y,i.z)] = [i]

    # Use list to get rid of extras
    l.debug("Checking list")
    for (location, pointsatloc) in pointcoords.items():
        if len(pointsatloc) > 1:
            for point in pointsatloc[1:]:
                for parent in set(point.parents):
                    parent.replacejwithi(pointsatloc[0], point)


def output():
    l.debug("Outputting XML")
    # First, set up a few data structures for optimization purposes
    global geometries, features
    nodes = [geometry for geometry in geometries if type(geometry) == Point]
    ways = [geometry for geometry in geometries if type(geometry) == Way]
    relations = [geometry for geometry in geometries if type(geometry) == Relation]
    featuresmap = {feature.geometry: feature for feature in features}

    w = XMLWriter(open(options.outputFile, 'w'))
    w.start("osm", version='0.6', generator='uvmogr2osm')

    for node in nodes:
        w.start("node", visible="true", id=str(node.id), lat=str(node.y), lon=str(node.x))
        if node in featuresmap:
            for (key, value) in featuresmap[node].tags.items():
                w.element("tag", k=key, v=value)
        w.end("node")

    for way in ways:
        w.start("way", visible="true", id=str(way.id))
        if way in featuresmap:
            if featuresmap[way].tags['oneway'] == 'yes' and featuresmap[way].tags['rDirection'] == 'yes':
                way.points.reverse()
        for node in way.points:
            w.element("nd", ref=str(node.id))
        if way in featuresmap:
            for (key, value) in featuresmap[way].tags.items():
                w.element("tag", k=key, v=value)
        w.end("way")

    for relation in relations:
        w.start("relation", visible="true", id=str(relation.id))
        for (member, role) in relation.members:
            w.element("member", type="way", ref=str(member.id), role=role)
        if relation in featuresmap:
            for (key, value) in featuresmap[relation].tags.items():
                w.element("tag", k=key, v=value)
        w.end("relation")

    w.end("osm")


# Main flow
data,data1,data2 = getFileData(sourceFile,sourceFile1,sourceFile2)
parseData(data,data1,data2)
mergePoints()
translations.preOutputTransform(geometries, features)
output()