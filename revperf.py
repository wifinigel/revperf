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

__author__ = "Nigel Bowden"
__version__ = "0.01"
__maintainer__ = "Nigel Bowden"
__email__ = "wifinigel@gmail.com"
__status__ = "Alpha"

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
    if protocol == 'udp':
        print("\nStarting tests with duration = {0} secs, port = {1}, protocol = {2}, interval = {3} secs, bandwidth = {4}kbps\n".format(duration, port, protocol,interval, bandwidth))
    else:
        print("\nStarting tests with duration = {0} secs, port = {1}, protocol = {2}, interval = {3} secs\n".format(duration, port, protocol,interval))
    
    # launch one test process per remote device
    for target_server in device_dict.keys():
    
        device_name = device_dict[target_server][0]
        
        iperf_proc = Process(target=iperf_client_test, args=(target_server, q, bandwidth, duration, port, protocol, interval))
        
        print('Connecting to {0} / {1}:{2}'.format(device_name, target_server, port))
        iperf_proc.start()  
        procs.append(iperf_proc)
    
    # All processes have completed to get to this point
    print('\nPlease wait while iperf3 tests complete...\n')

    for a_proc in procs:
        #block main process until sub-processes complete
        a_proc.join()

    # Provide details of test results
    print("\nAll processes complete...here are the results:\n")
    
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