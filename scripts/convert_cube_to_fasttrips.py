import copy,datetime,getopt,logging,os,shutil,sys,time
import getopt
from dbfpy import dbf

# use Wrangler from the same directory as this build script
sys.path.insert(0, os.path.join(os.path.dirname(__file__),".."))
sys.path.append(r"Y:\champ\releases\5.0.0\lib")
import Wrangler
from Wrangler.Logger import WranglerLogger
from Wrangler.TransitNetwork import TransitNetwork
from Wrangler.TransitLink import TransitLink
from Wrangler.TransitLine import TransitLine
from Wrangler.HelperFunctions import *
#from Wrangler.FareParser import FareParser, fare_file_def  # should probably be moved into TransitNetwork.
from Wrangler.Fare import ODFare, XFFare, FarelinksFare
from Wrangler.Regexes import *
from Wrangler.NetworkException import NetworkException
from _static.Cube import CubeNet

import Lookups
from SkimUtil import Skim, HighwaySkim, WalkSkim

USAGE = """

  python convert_cube_to_fasttrips.py network_specification.py

  reads in a Cube Highway and Transit Network and writes out fast-trips network files.
"""

###############################################################################
#                                                                             #
#              Define the following in an input configuration file            #
#                                                                             #
###############################################################################

TIMEPERIODS = Lookups.Lookups.TIMEPERIODS_NUM_TO_STR
CUBE_FREEFLOW = r'Q:\Model Development\SHRP2-fasttrips\Task2\network_translation\input_champ_network\freeflow\hwy\FREEFLOW.NET'
HWY_LOADED  = r'Q:\Model Development\SHRP2-fasttrips\Task2\network_translation\input_champ_network\trn'
# transit[tod].lin with dwell times, xfer_supplinks, and walk_drive_access:
TRN_LOADED  = r'Q:\Model Development\SHRP2-fasttrips\Task2\network_translation\input_champ_network\trn'
# .link (off-street link) and fares:
TRN_BASE    = r'Q:\Model Development\SHRP2-fasttrips\Task2\network_translation\input_champ_network\freeflow\trn'
TRANSIT_CAPACITY_DIR = r'Y:\networks\TransitVehicles'
FT_OUTPATH  = r'Q:\Model Development\SHRP2-fasttrips\Task2\network_translation\testing\fast-trips'
CHAMP_NODE_NAMES = r'Y:\champ\util\nodes.xls'
MODEL_RUN_DIR = r'X:\Projects\TIMMA\2012_Base_v2'       # for hwy and walk skims
SMALL_SUPPLINKS = r'Q:\Model Development\SHRP2-fasttrips\Task2\network_translation\input_champ_network\small_supplinks'

if __name__=='__main__':
    opts, args = getopt.getopt(sys.argv[1:],"s:h:f:v:t:")

    do_supplinks    = True
    do_highways     = True
    do_fares        = True
    do_vehicles     = True
    test            = False
    ask_raw_input   = False
    
    for o, a in opts:
        if o == '-s' and a == 'False':
            do_supplinks = False
        if o == '-h' and a == 'False':
            do_highways = False
        if o == '-f' and a == 'False':
            do_fares = False
        if o == '-v' and a == 'False':
            do_vehicles = False
        if o == '-t' and a == 'test':
            test = True
    
    # set up logging    
    NOW = time.strftime("%Y%b%d.%H%M%S")
    FT_OUTPATH = os.path.join(FT_OUTPATH,NOW)    
    if not os.path.exists(FT_OUTPATH): os.mkdir(FT_OUTPATH)                         
    LOG_FILENAME = os.path.join(FT_OUTPATH,"convert_cube_to_fasttrips_%s.info.LOG" % NOW)
    Wrangler.setupLogging(LOG_FILENAME, LOG_FILENAME.replace("info", "debug"))
    os.environ['CHAMP_NODE_NAMES'] = CHAMP_NODE_NAMES

    # Get transit network
    WranglerLogger.debug("Creating transit network.")
    transit_network = TransitNetwork(5.0)
    transit_network.mergeDir(TRN_BASE)
    transit_network.convertTransitLinesToFastTripsTransitLines()

    if do_vehicles:
        WranglerLogger.debug("Getting transit capacity.")
        Wrangler.TransitNetwork.capacity = Wrangler.TransitCapacity(directory=TRANSIT_CAPACITY_DIR)
        # build dict of vehicle types
        for line in transit_network.lines:
            ##transit_freqs_by_line[line.name] = line.getFreqs()
            if isinstance(line, str):
                continue
            vehicles = {'AM': Wrangler.TransitNetwork.capacity.getSystemAndVehicleType(line.name, "AM")[1],
                        'MD': Wrangler.TransitNetwork.capacity.getSystemAndVehicleType(line.name, "MD")[1],
                        'PM': Wrangler.TransitNetwork.capacity.getSystemAndVehicleType(line.name, "PM")[1],
                        'EV': Wrangler.TransitNetwork.capacity.getSystemAndVehicleType(line.name, "EV")[1],
                        'EA': Wrangler.TransitNetwork.capacity.getSystemAndVehicleType(line.name, "EA")[1]}
            line.setVehicleTypes(vehicles)
            
    if do_highways:
        WranglerLogger.debug("Reading highway networks to get node coordinates and link attributes")
        highway_networks = {}
        for tod in TIMEPERIODS.itervalues():
            cube_net    = os.path.join(HWY_LOADED,'LOAD%s_XFERS.NET' % tod)
            if not os.path.exists(os.path.join(FT_OUTPATH,'loaded_highway_data')): os.mkdir(os.path.join(FT_OUTPATH,'loaded_highway_data'))
            links_csv   = os.path.join(FT_OUTPATH,'loaded_highway_data','LOAD%s_XFERS.csv' % tod)
            nodes_csv   = os.path.join(FT_OUTPATH,'loaded_highway_data','LOAD%s_XFERS_nodes.csv' % tod)

            # get loaded network links w/ bus time and put it into dict highway_networks with time-of-day as the key
            # i.e. highway networks[tod] = links_dict
            (nodes_dict, links_dict) = CubeNet.import_cube_nodes_links_from_csvs(cube_net, extra_link_vars=['BUSTIME'], links_csv=links_csv, nodes_csv=nodes_csv)
            highway_networks[tod] = links_dict
        WranglerLogger.debug("adding xy to Nodes")
        transit_network.addXY(nodes_dict)
        WranglerLogger.debug("adding travel times to all lines")
        transit_network.addTravelTimes(highway_networks)
        WranglerLogger.debug("add pnrs")
        transit_network.createFastTrips_PNRs(nodes_dict)
            
    if do_supplinks:
        WranglerLogger.debug("Merging supplinks.")
        transit_network.mergeSupplinks(TRN_LOADED)
        ##transit_network.mergeSupplinks(SMALL_SUPPLINKS)
        WranglerLogger.debug("\tsetting up walk skims for access links.")
        walkskim = WalkSkim(file_dir = MODEL_RUN_DIR)
        nodeToTazFile = os.path.join(MODEL_RUN_DIR,"nodesToTaz.dbf")
        nodesdbf      = dbf.Dbf(nodeToTazFile, readOnly=True, new=False)
        nodeToTaz     = {}
        maxTAZ        = 0
        for rec in nodesdbf:
            nodeToTaz[rec["N"]] = rec["TAZ"]
            maxTAZ = max(maxTAZ, rec["TAZ"])
        nodesdbf.close()

        WranglerLogger.debug("\tsetting up highway skims for access links.")
        hwyskims = {}
        for tpnum,tpstr in Skim.TIMEPERIOD_NUM_TO_STR.items():
            hwyskims[tpnum] = HighwaySkim(file_dir=MODEL_RUN_DIR, timeperiod=tpstr) 
        pnrTAZtoNode = {}
        pnrZonesFile = os.path.join(MODEL_RUN_DIR,"PNR_ZONES.dbf")
        if not os.path.exists(pnrZonesFile):
            WranglerLogger.fatal("Couldn't open %s" % pnrZonesFile)
            sys.exit(2)
        indbf = dbf.Dbf(os.path.join(MODEL_RUN_DIR,"PNR_ZONES.dbf"), readOnly=True, new=False)
        for rec in indbf:
            pnrTAZtoNode[rec["PNRTAZ"]] = rec["PNRNODE"]
        indbf.close()
        pnrNodeToTAZ = dict((v,k) for k,v in pnrTAZtoNode.iteritems())
        # print self.pnrTAZtoNode
        
        maxRealTAZ = min(pnrTAZtoNode.keys())-1
        WranglerLogger.debug("\tconverting supplinks to fasttrips format.")
        transit_network.getFastTripsSupplinks(walkskim,nodeToTaz,maxTAZ,hwyskims,pnrNodeToTAZ)

    if do_fares:
        WranglerLogger.debug("Making FarelinksFares unique")
        transit_network.makeFarelinksUnique()
        WranglerLogger.debug("creating zone ids")
        transit_network.createZoneIDsFromFares()
        nodeNames = getChampNodeNameDictFromFile(os.environ["CHAMP_node_names"])
        WranglerLogger.debug("Adding station names to OD Fares")
        transit_network.addStationNamestoODFares(nodeNames)
        WranglerLogger.debug("adding fares to lines")
        transit_network.addFaresToLines()
        transit_network.createFastTrips_Fares()
        
    WranglerLogger.debug("adding first departure times to all lines")
    transit_network.addFirstDeparturesToAllLines()
    
    WranglerLogger.debug("writing agencies")
    transit_network.writeFastTrips_Agency(path=FT_OUTPATH)
    if do_vehicles:
        WranglerLogger.debug("writing vehicles")
        transit_network.writeFastTrips_Vehicles(path=FT_OUTPATH)
    WranglerLogger.debug("writing lines")
    transit_network.writeFastTrips_Shapes(path=FT_OUTPATH)
    WranglerLogger.debug("writing routes")
    transit_network.writeFastTrips_Routes(path=FT_OUTPATH)
    WranglerLogger.debug("writing stop times")
    transit_network.writeFastTrips_Trips(path=FT_OUTPATH)
    if do_fares:
        WranglerLogger.debug("writing fares")
        transit_network.writeFastTrips_Fares(path=FT_OUTPATH)
    WranglerLogger.debug("writing stops")
    transit_network.createFastTrips_Nodes()
    transit_network.writeFastTrips_Stops(path=FT_OUTPATH)
    if do_highways:
        WranglerLogger.debug("writing pnrs")
        transit_network.writeFastTrips_PNRs(path=FT_OUTPATH)
    WranglerLogger.debug("Writing supplinks")
    transit_network.writeFastTrips_Access(path=FT_OUTPATH)

    if test:
        print "testing"

        node_to_zone_file = 'node_to_zone_file_%s.log' % NOW
        ntz = open(node_to_zone_file,'w')
        ntz.write('node,type,zone,type\n')
        for zone, nodes in transit_network.zone_to_nodes.iteritems():
            for this_node in nodes:
                ntz.write('%s,%s,%s,%s\n' % (str(this_node),type(this_node),str(zone),type(zone)))
            overlap_list = []
            for nodes2 in transit_network.zone_to_nodes.values():
                for n in nodes:
                    if n in nodes2 and nodes != nodes2 and n not in overlap_list: overlap_list.append(n)        
            WranglerLogger.debug("ZONE: %d HAS %d of %d NODES OVERLAP WITH OTHER ZONES" % (zone, len(overlap_list), len(nodes)))
            #WranglerLogger.debug("%s" % str(overlap_list))
        if ask_raw_input: raw_input("Reporting Fares Parsed (XFFares) press enter to proceed.")
        WranglerLogger.debug("Reporting Fares Parsed (XFFares) press enter to proceed.")
        for xf_fare in transit_network.xf_fares:
            if isinstance(xf_fare,XFFare): WranglerLogger.debug('%s' % str(xf_fare))
        if ask_raw_input: raw_input("Reporting Fares Parsed (ODFares) press enter to proceed.")
        WranglerLogger.debug("Reporting Fares Parsed (ODFares) press enter to proceed.")
        for od_fare in transit_network.od_fares:
            if isinstance(od_fare,ODFare): WranglerLogger.debug('%s' % str(od_fare))
        if ask_raw_input: raw_input("Reporting Fares Parsed (FarelinksFares) press enter to proceed.")
        WranglerLogger.debug("Reporting Fares Parsed (FarelinksFares) press enter to proceed.")
        for farelinks_fare in transit_network.farelinks_fares:
            if isinstance(farelinks_fare,FarelinksFare):
                WranglerLogger.debug('%s' % str(farelinks_fare))
        if ask_raw_input: raw_input("done reporting Fares.")


        outfile = open(os.path.join(FT_OUTPATH,'links.csv'),'w')
        #print "NUM LINKS", len(transit_network.links)
        for link in transit_network.links:
            if isinstance(link, TransitLink):
                outfile.write('%d,%d,\"%s\"\n' % (link.Anode,link.Bnode,link.id))
            elif isinstance(link, str):
                outfile.write('%s\n' % link)
            else:
                print "Unhandled data type %s" % type(link)
                raise NetworkException("Unhandled data type %s" % type(link))
        transit_network.write(os.path.join(FT_OUTPATH,'test_champnet_out'), cubeNetFileForValidation = CUBE_FREEFLOW)
        print "Checking lines for BUSTIME"
        for line in transit_network.lines:
            if isinstance(line, TransitLine):
                for link_id, link_values in line.links.iteritems():
                    if isinstance(link_values, TransitLink):
                        if line['FREQ[1]'] != 0 and 'BUSTIME_AM' not in link_values.keys():
                            print '%s, %s: Missing BUSTIME for AM' % (line.name, link_values.id)
                        if line['FREQ[2]'] != 0 and 'BUSTIME_MD' not in link_values.keys():
                            print '%s, %s: Missing BUSTIME for MD' % (line.name, link_values.id)
                        if line['FREQ[3]'] != 0 and 'BUSTIME_PM' not in link_values.keys():
                            print '%s, %s: Missing BUSTIME for PM' % (line.name, link_values.id)
                        if line['FREQ[4]'] != 0 and 'BUSTIME_EV' not in link_values.keys():
                            print '%s, %s: Missing BUSTIME for EV' % (line.name, link_values.id)
                        if line['FREQ[5]'] != 0 and 'BUSTIME_EA' not in link_values.keys():
                            print '%s, %s: Missing BUSTIME for EA' % (line.name, link_values.id)
        transit_network.writeFastTripsFares_dumb(path=FT_OUTPATH)
        
##        for id in transit_network.line("MUN5I").links:
##            print id, transit_network.line("MUN5I")