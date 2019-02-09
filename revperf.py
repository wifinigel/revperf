#!/usr/bin/python
'''
A script that establishes simultaneous reverse iperf3 tests to a number of 
remote devices (running iper3 server) and summarizes the results output
generatd by each.

This has been developed on the WLANPi and requires no additional Python modules
to those found on the standard WLANPi image

'''

from __future__ import print_function, unicode_literals, division
import ConfigParser
import csv
from multiprocessing import Process, current_process, Queue, Lock
import subprocess
import os
import os.path
import sys
import json
import getopt

__author__ = "Nigel Bowden"
__version__ = "0.02"
__maintainer__ = "Nigel Bowden"
__email__ = "wifinigel@gmail.com"
__status__ = "Alpha"

DEBUG = 0
PING_TEST = True
PERF_TEST = True

# we must be root to run this script - exit with msg if not
if not os.geteuid()==0:
    print("\n#####################################################################################")
    print("You must be root to run this script (use 'sudo ./revperf.py') - exiting" )
    print("#####################################################################################\n")
    sys.exit()

def usage():

    # put CLI syntax here
    print('\nUsage: revperf.py -n ')
    print('       revperf.py -p ')
    print('       revperf.py -v ')
    print('       revperf.py -h \n')
    print('  -h      Help information')
    print('  -n      No ping checks prior to test start (only do iperf tests)')
    print('  -p      Ping only tests (do not do iperf tests)')
    print('  -v      Script verion information')
    print('\n')
    print('revperf home page: https://github.com/wifinigel/revperf \n')
    sys.exit()

def ping_host(host):

    # ICMP ping to host and report pass/fail (True/False)
    try:
        ping_output = subprocess.check_output("/bin/ping -c 2 -q " + host, shell=True)
        return True
    except Exception as ex:
        if DEBUG:
            error_descr = "Ping issue:"
            print(error_descr)
            print(ex)
        
        return False 

def iperf_client_test(target_server, q, bandwidth=0, duration=10, port=5201, protocol='tcp', interval=5):

    '''
    Worker process that performs iperf test to each remote device
    '''

    # Verify if protocol value valid
    if protocol == 'udp':
        protocol = '-u'
    elif protocol == 'tcp':
        protocol = ''
        # fix bandwidth unlimited for TCP
        bandwidth = 0
    else:
        print("!!! Invalid value for protocol (should be 'tcp' or 'udp') :" + protocol)
        return
    
    iperf_location = '/usr/bin/iperf3'
    
    try:
        # (add -J to get json output)
        iperf_info = subprocess.check_output("{0} -R -c {1} -i {2} -t {3} -p {4} {5} -b {6}K 2>&1".format(iperf_location, target_server, interval, duration, port, protocol, bandwidth), shell=True)
    except Exception as ex:
        iperf_info = "#" * 100
        iperf_info += "\nIssue with iperf_process:" 
        iperf_info += "\n" + str(ex) + "\n"
        iperf_info += "(Check for connectivity issues)\n"
        iperf_info += "#" * 100
        iperf_info += "\n\n"
   
    #q.put([target_server, json.loads(iperf_info)])
    q.put([target_server, iperf_info])
    return 

        
def main():

    global PING_TEST
    global PERF_TEST

    # process sthe CLI parameters passed to this script 
    try:
        opts, args = getopt.getopt(sys.argv[1:],'nhvp')
    except getopt.GetoptError:
        print("\nOops...syntaxt error, please re-check: \n")
        usage()

    for opt, arg in opts:
        if opt == '-h':
            usage()
        elif opt == ("-v"):
            print('\n revperf.py')
            print(' Version: ' + __version__ + '\n')
            sys.exit()
        elif opt in ("-n"):
            PING_TEST = False
        elif opt in ("-p"):
            PERF_TEST = False

    '''
    1. Read in CSV file with target device details
    2. Read in config file with iperf parameters for tests
    3. Launch all worker processes
    4. Print all results to STDOUT
    '''
    device_dict = {}

    # Read in devices from CSV file (format: ip, name, "description")
    device_file = os.path.dirname(os.path.realpath(__file__)) + "/devices.csv"
    
    with open(device_file, 'rb') as f:
        reader = csv.DictReader(f)
        try:
            for row in reader:
                
                device_ip = row['device_ip']
                device_name = row['device_name']
                device_description = row['device_description']
                
                device_dict[device_ip] = [device_name, device_description]
                
        except csv.Error as e:
            sys.exit('file %s, line %d: %s' % (filename, reader.line_num, e))

    # Read in config file (config.ini in same dir as script)
    config_vars = {}
    
    config = ConfigParser.SafeConfigParser()
    config_file = os.path.dirname(os.path.realpath(__file__)) + "/config.ini"
    
    # exit if config file not found
    if not os.path.exists(config_file):
        print("!!! Config file does not exist: " + config_file)
        sys.exit()
    
    config.read(config_file)

    duration = config.get('Iperf', 'test_duration')
    port = config.get('Iperf', 'port')
    protocol = (config.get('Iperf', 'protocol')).lower()
    interval = config.get('Iperf', 'report_interval')
    bandwidth = config.get('Iperf', 'bandwidth')
    
    procs = []
    
    # function args
    target_server = ''
    q = Queue()

    # provide status message showing test details
    print('_' * 80)
    if protocol == 'udp':
        print("Starting tests with following parameters: \n\n duration  = {0} secs \n port      = {1} \n protocol  = {2} \n interval  = {3} secs \n bandwidth = {4}kbps\n".format(duration, port, protocol,interval, bandwidth))
    else:
        print("Starting tests following parameters: \n\n duration  = {0} secs \n port      = {1} \n protocol  = {2} \n interval  = {3} secs\n".format(duration, port, protocol,interval))
    
    print('Information: Hit Ctrl-C at ay time to stop testing.')
    print('Information: Ensure all remote test devices are running iperf3 in server mode (not iperf2)')
    print('_' * 80)
    print('\n')
    
    #######################
    # Ping tests
    #######################
    # try pinging the test servers to verify if they are accessible
    if PING_TEST == True:
    
        print('-' * 80)
        print("Performing ping test to each target iperf server...\n")
    
        for target_server in device_dict.keys():
            
            if ping_host(target_server):
                print(" + Test ping to device: {} ({}): ping test passed". format(device_dict[target_server][0], target_server))
            else:
                print(" * Test ping to device: {} ({}): ping test failed ***". format(device_dict[target_server][0], target_server))
                
        print("\nPing tests complete (servers that fail ping tests may able to run iperf tests).")
        print('-' * 80)
        print('\n')
        
    if PERF_TEST == False:
        sys.exit()
    
    #######################
    # Process launches
    #######################
    # launch one test process per remote device
    print('+' * 80)
    print("Commencing iperf tests...\n")
   
    for target_server in device_dict.keys():
    
        device_name = device_dict[target_server][0]
        
        iperf_proc = Process(target=iperf_client_test, args=(target_server, q, bandwidth, duration, port, protocol, interval))
        
        print(' * Connecting to {0} / {1}:{2}'.format(device_name, target_server, port))
        iperf_proc.start()  
        procs.append(iperf_proc)
    
    # All processes have completed to get to this point
    print('\nPlease wait while iperf3 tests complete...\n')
    print('+' * 80)

    for a_proc in procs:
        #block main process until sub-processes complete
        a_proc.join()

    # Provide details of test results
    print("\nAll tests complete...here are the results:\n")
    
    # Process the results that have been dumped in to the queue by each process
    while not q.empty():
        result = q.get()
        
        # test result details
        ip_address = result[0]
        test_output = result[1]
        
        # derive device details from IP address
        device_name = device_dict[ip_address][0]
        device_description = device_dict[ip_address][1]
        
        print("=" * 80)
        print("Results for {0} / {1}   {2}".format(device_name, ip_address, device_description))
        print("=" * 80)
        print(test_output)

if __name__ == "__main__":
    main()