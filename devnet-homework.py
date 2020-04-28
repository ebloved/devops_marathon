from netmiko import ConnectHandler
from netmiko.ssh_exception import NetmikoAuthenticationException
from netmiko.ssh_exception import NetmikoTimeoutException
import sys
import csv
import datetime
import os
import re

DEVICES_FILE_NAME = 'devices.csv' #File to store FQDN/addresses + cridentials
DEVICES_BACKUP_DIR = 'backups/' #Backup directory
DEVICES_RESULT_FILE = 'devices_result.txt' #Temporary file to store query results. Clears every run.
devices_list = []




def get_time(): #Returns date/time in YMD-hms format
    now = datetime.datetime.now()
    return now.strftime("%Y_%m_%d-%H_%M_%S")

def append_to_file(filename): #To write to temporary file
    with open(DEVICES_RESULT_FILE, 'a') as file:
        file.write(filename + ' | ')

def get_device_list(DEVICES_FILE_NAME): #Read and parse .csv file and store device's values (address, port, username etc.) to dict
    with open(DEVICES_FILE_NAME, 'r') as devices_file:
        devices_list_temp = csv.DictReader(devices_file, delimiter="|")
        for row in devices_list_temp:
            devices_list.append(row)
    return devices_list

def connect_to_device(device): #Connect to device. Auth/timeout check included.
    try:
        print('Connecting to ', device['host'])
        connection = ConnectHandler(
            device_type = device['device_type'],
            host = device['host'],
            username = device['username'],
            password = device['password'],
            port = device['port']
        )
        print('Connected!')
        print('--*--'*10)

    except (NetmikoAuthenticationException): 
        print('Authentication fail')
        return

    except (NetmikoTimeoutException):
        print('Connection timed out')
        return
    return connection

def create_backup(hostname, timestamp, connection): #Create running config backup.
    backup_filename = DEVICES_BACKUP_DIR +  hostname + "/" + hostname + '_' + timestamp + '.txt'
    connection.enable()
    output = connection.send_command('sh run')
    if not os.path.exists(os.path.join(DEVICES_BACKUP_DIR, hostname)):
        os.mkdir(os.path.join(DEVICES_BACKUP_DIR, hostname))
    with open(backup_filename, 'w') as file:
        file.write(output)
        print('BACKUP SUCCESFULL')

def get_device_version(connection, hostname): #Get device version via regexp 
    output = connection.send_command('show ver | i Software \(')
    ver = re.findall(r'\(.{6,50}\)', output)
    ver = str(ver)
    append_to_file(ver)
    return ver

def check_NPE(version): #Checking NPE with data from "get_device_version"
    NPE = re.findall(r'NPE', version)
    if NPE:
        NPE = "NPE"
    else:
        NPE = "PE"
    append_to_file(NPE)   
    return

def check_cdp(connection, hostname): #Checking CDP version and peers
    output = connection.send_command('sh cdp')
    cdp = output.split()
    if cdp[-2] == 'not':
        cdp_result = 'CDP is OFF'
    else:
        cdp_nei = connection.send_command('sh cdp nei')
        cdp_nei = cdp_nei.split()
        cdp_result = 'CDP is ON, '+ cdp_nei[-1] + ' peers'
    print('CDP RESULT - ' + cdp_result)
    append_to_file(cdp_result)
    return cdp_result

def check_ntp(connection, device): #Checking NTP. It's my personal hell. It's working, I hope.
    output = connection.send_command('ping 194.190.168.1')
    output = re.findall(r'Success\D*\d\d', output)
    if output:
        print('NTP server check success')
        print("Setting timezone")
        connection.send_config_set('clock timezone GMT 0 0')
        print("Setting NTP server")
        connection.send_config_set('ntp server 192.168.1.1 prefer')
        print('Checking NTP status')
        output = connection.send_command('sh ntp status | i Clock')
        output = output.split()
        if output[2] == 'unsynchronized,':
            ntp_status = "NTP not in sync"
        else:
            ntp_status = "NTP in sync"
    else:
        print('NTP server unreachable')
        ntp_status = "NTP not in sync"
    print("NTP STATUS - " + ntp_status)
    with open(DEVICES_RESULT_FILE, 'a') as file:
        file.write(ntp_status + '\n')
    return ntp_status

def get_hostname(connection): #Nothing more, than function, that returns hostname
    hostname = connection.find_prompt()
    hostname = hostname[:-1]
    append_to_file(hostname)

def get_device_type(connection): #And another one, returns device_type
    device_type = connection.send_command('sh ver | i ^cisco')
    device_type = device_type.split()
    print('DEVICE TYPE - ' + device_type[1])
    append_to_file(device_type[1])

def main(*args):
    device_result = {}
    get_device_list(DEVICES_FILE_NAME)
    timestamp = get_time()
    #Opening temp result file, filling it with timestamp and \n. Needed because I don't know how else I can open file for writing at the beginning
    with open(DEVICES_RESULT_FILE, 'w') as file:
        file.write('File created: ' + timestamp + '\n')
        file.close()
    #Creating connection to device    
    for device in devices_list:
        try: connection =  connect_to_device(device)
        except NameError: connection = None   
        if connection is not None:
            #If connection created, filling temp result file with some data
            get_hostname(connection)
            get_device_type(connection)
            device_version = get_device_version(connection, device['host'])
            check_NPE(device_version)
            check_cdp(connection, device['host'])
            create_backup(device['host'], timestamp, connection)
            check_ntp(connection, device['host'])
            #Closing connection
            connection.disconnect()
    #Printing results from temp file
    with open(DEVICES_RESULT_FILE, 'r') as file:
        result = file.read()
        print(result)         
            

#I don't exactly understood how it's working. Gracefully stolen from OTselova backup script.
if __name__ == '__main__':
    # checking if we run independently
    _, *script_args = sys.argv
    
    # the execution starts here
    main(*script_args)
