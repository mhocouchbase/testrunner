import json
import time
from threading import Thread, Event
from basetestcase import BaseTestCase
from couchbase_helper.document import DesignDocument, View
from couchbase_helper.documentgenerator import DocumentGenerator
from membase.api.rest_client import RestConnection
from membase.helper.rebalance_helper import RebalanceHelper
from membase.api.exception import ReadDocumentException
from membase.api.exception import DesignDocCreationException
from membase.helper.cluster_helper import ClusterOperationHelper
from remote.remote_util import RemoteMachineShellConnection
from random import randint
from datetime import datetime
import time
import commands
import logger
log = logger.Logger.get_logger()

class audit:
    AUDITLOGFILENAME = 'audit.log'
    AUDITCONFIGFILENAME = 'audit.json'
    AUDITDESCFILE = 'audit_events.json'
    WINLOGFILEPATH = "C:/Program Files/Couchbase/Server/var/lib/couchbase/logs"
    LINLOGFILEPATH = "/opt/couchbase/var/lib/couchbase/logs"
    WINCONFIFFILEPATH = "C:/Program Files/Couchbase/Server/var/lib/couchbase/config/"
    LINCONFIGFILEPATH = "/opt/couchbase/var/lib/couchbase/config/"

    def __init__(self,
                 eventID=None,
                 host=None,
                 method='REST'):

        self.method = method
        self.host = host
        self.pathDescriptor = self.getAuditConfigElement("descriptors_path") + "/"
        # self.pathLogFile = self.getAuditConfigElement('log_path')
        # self.archiveFilePath = self.getAuditConfigElement('archive_path')
        self.pathLogFile = self.getAuditLogPath()
        self.archiveFilePath = self.getArchivePath()
        self.auditConfigPath = self.getAuditConfigPathInitial()
        self.defaultFields = ['id', 'name', 'description']
        if (eventID is not None):
            self.eventID = eventID
            self.eventDef = self.returnEventsDef()


    def getAuditConfigPathInitial(self):
        shell = RemoteMachineShellConnection(self.host)
        os_type = shell.extract_remote_info().distribution_type
        log.info ("OS type is {0}".format(os_type))
        if os_type == 'CentOS':
            auditconfigpath = audit.LINCONFIGFILEPATH
            self.currentLogFile = audit.LINLOGFILEPATH
        else:
            auditconfigpath = audit.WINCONFIFFILEPATH
            self.currentLogFile = audit.WINLOGFILEPATH
        return auditconfigpath

    '''
    setAuditConfigPath - External function to set configPATH
    Parameters:
    configPath - path to config file
    Returns : None
    '''
    def setAuditConfigPath(self, configPath):
        self.auditConfigPath = configPath

    '''
    getAuditConfigPath
    Returns - Path to audit config file
    '''
    def getAuditConfigPath(self):
        return self.auditConfigPath

    '''
    readFile - copy file to local '/tmp' directory
    Parameters:
        pathAuditFile - remove file path 
        fileName - file that needs to be copied
    Returns:
        None
    '''
    def getRemoteFile(self, host, remotepath, filename):
        shell = RemoteMachineShellConnection(host)
        try:
            sftp = shell._ssh_client.open_sftp()
            tempfile = str(remotepath + filename)
            tmpfile = "/" + filename
            log.info ("Value of remotepath is {0} and current Path - {1}".format(tempfile, tmpfile))
            sftp.get('{0}'.format(tempfile), '{0}'.format(tmpfile))
            sftp.close()
        except Exception, e:
            log.info (" Value of e is {0}".format(e))
            shell.disconnect()


    def readFile(self, pathAuditFile, fileName):
        self.getRemoteFile(self.host, pathAuditFile, fileName)

    '''
    writeFile - writing the config file
    Parameters:
        pathAuditFile - path to audit config
        fileName - name of audit config file
        lines - lines that need to be copied
    Returns:
        none
    '''
    def writeFile(self, pathAuditFile=None, fileName=None, lines=None):
        if (pathAuditFile is None):
            pathAuditFile = self.getAuditConfigPathInitial()
        if (fileName is None):
            fileName = audit.AUDITCONFIGFILENAME
        shell = RemoteMachineShellConnection(self.host)
        try:
            with open ("/tmp/audit.json", 'w') as outfile:
                json.dump(lines, outfile)
            result = shell.copy_file_local_to_remote('/tmp/audit.json', pathAuditFile + fileName)
        finally:
            shell.disconnect()

    '''
    returnEvent - reads actual audit event from audit.log file and returns last event 
    Parameters:
        eventNumber - event number that needs to be queried
    Returns:
        dictionary of actual event from audit.log
    '''
    def returnEvent(self, eventNumber):
        data = []
        self.readFile(self.pathLogFile, audit.AUDITLOGFILENAME)
        with open('/' + audit.AUDITLOGFILENAME) as f:
            for line in f:
                tempJson = json.loads(line)
                if (tempJson['id'] == eventNumber):
                    data.append(json.loads(line))
        return data[len(data) - 1]

    '''
    getAuditConfigElement - get element of a configuration file
    Parameters
        element - element from audit config file
    Returns
        element of the config file or entire file if element == 'all'
    '''
    def getAuditConfigElement(self, element):
        data = []
        self.readFile(self.getAuditConfigPathInitial(), audit.AUDITCONFIGFILENAME)
        json_data = open ("/" + audit.AUDITCONFIGFILENAME)
        data = json.load(json_data)
        if (element == 'all'):
            return data
        else:
            return data[element]

    '''
    returnEventsDef - read event definition
    Parameters:None
    Returns:
        list of events from audit_events.json file
    '''
    def returnEventsDef(self):
        data = []
        self.readFile(self.pathDescriptor, audit.AUDITDESCFILE)
        json_data = open ("/" + audit.AUDITDESCFILE)
        data = json.load(json_data)
        return data

    '''
    getAuditLogPath - return value of log_path from REST API
    Returns:
        returns log_path from audit config file
    '''
    def getAuditLogPath(self):
        rest = RestConnection(self.host)
        content = rest.getAuditSettings()
        return content['log_path'] + "/"

    '''
    getArchivePath - return value of archive_path from REST API
    Returns:
        returns archive_path from audit config file
    '''
    def getArchivePath(self):
        rest = RestConnection(self.host)
        content = rest.getAuditSettings()
        return content['archive_path'] + "/"

    '''
    getAuditStatus - return value of audit status from REST API
    Returns:
        returns audit status from audit config file
    '''
    def getAuditStatus(self):
        rest = RestConnection(self.host)
        content = rest.getAuditSettings()
        return content['auditd_enabled']

    '''
    getAuditRotateInterval - return value of rotate Interval from REST API
    Returns:
        returns audit status from audit config file
    '''
    def getAuditRotateInterval(self):
        rest = RestConnection(self.host)
        content = rest.getAuditSettings()
        return content['rotate_interval']

    '''
    setAuditLogPath - set log_path via REST API
    Parameter:
        auditLogPath - path to log_path
    Returns:
        status - status rest command
    '''
    def setAuditLogPath(self, auditLogPath):
        rest = RestConnection(self.host)
        status = rest.setAuditSettings(logPath=auditLogPath, archivePath=self.currentLogFile)
        return status

    '''
    setAuditArchivePath - set archive_path via REST API
    Parameter:
        archivePath - path to archive_path
    Returns:
        status - status rest command
    '''
    def setAuditArchivePath(self, archivePath):
        rest = RestConnection(self.host)
        status = rest.setAuditSettings(archivePath=archivePath, logPath=self.currentLogFile)
        return status

    '''
    setAuditEnable - set audit_enabled via REST API
    Parameter:
        audit_enabled - true/false for setting audit status
    Returns:
        status - status rest command
    '''
    def setAuditEnable(self, auditEnable):
        rest = RestConnection(self.host)
        status = rest.setAuditSettings(enabled=auditEnable, archivePath=self.currentLogFile, logPath=self.currentLogFile)
        return status

    '''
    checkConfig - Wrapper around audit class
    Parameters:
        expectedResult - dictionary of fields and value for event
    '''
    def checkConfig(self, expectedResults):
        fieldVerification, valueVerification = self.validateEvents(expectedResults)
        self.assertTrue(fieldVerification, "One of the fields is not matching")
        self.assertTrue(valueVerification, "Values for one of the fields is not matching")

    '''
    setAuditRotateInterval - set rotate_internval via REST API
    Parameter:
        rotate_internval - log rotate interval
    Returns:
        status - status rest command
    '''
    def setAuditRotateInterval(self, rotateInterval):
        rest = RestConnection(self.host)
        status = rest.setAuditSettings(rotateInterval=rotateInterval, archivePath=self.archiveFilePath, logPath=self.currentLogFile)
        return status

    '''
    getTimeStampFirstEvent - timestamp of first event in audit.log
    Returns:
        timestamp of first event in audit.log
    '''
    def getTimeStampFirstEvent(self):
        self.readFile(self.pathLogFile, audit.AUDITLOGFILENAME)
        with open('/tmp/' + audit.AUDITLOGFILENAME) as f:
            data = line = f.readline()
        data = ((json.loads(line))['timestamp'])[:19]
        return data


    '''
    returnFieldsDef - returns event definition separated by sections
    Parameters:
        data - audit_events.json file in a list of dictionary
        eventNumber - event number that needs to be queried
    Returns:
        defaultFields - dictionary of default fields
        mandatoryFields - list is dictionary of mandatory fields
        mandatorySecLevel - list of dictionary containing 2nd level of mandatory fields
        optionalFields - list is dictionary of optional fields
        optionalSecLevel - list of dictionary containing 2nd level of optional fields
    '''
    def returnFieldsDef(self, data, eventNumber):
        defaultFields = {}
        mandatoryFields = []
        mandatorySecLevel = []
        optionalFields = []
        optionalSecLevel = []
        fields = ['mandatory_fields', 'optional_fields']
        for items in data['modules']:
            for particulars in items['events']:
                if particulars['id'] == eventNumber:
                    for key, value in particulars.items():
                        if (key not in fields):
                            defaultFields[key] = value
                        elif key == 'mandatory_fields':
                            for items in particulars['mandatory_fields']:
                                mandatoryFields.append(items)
                                if (isinstance((particulars['mandatory_fields'][items.encode('utf-8')]), dict)):
                                    tempStr = items
                                    for secLevel in particulars['mandatory_fields'][items].items():
                                        tempStr = tempStr + ":" + secLevel[0]
                                    mandatorySecLevel.append(tempStr)
                        elif key == 'optional_fields':
                            for items in particulars['optional_fields']:
                                optionalFields.append(items)
                                if (isinstance((particulars['optional_fields'][items.encode('utf-8')]), dict)):
                                    tempStr = items
                                    for secLevel in particulars['optional_fields'][items].items():
                                        tempStr = tempStr + ":" + secLevel[0]
                                    optionalSecLevel.append(tempStr)

        log.info ("Value of default fields is - {0}".format(defaultFields))
        log.info ("Value of mandatory fields is {0}".format(mandatoryFields))
        log.info ("Value of mandatory sec level is {0}".format(mandatorySecLevel))
        log.info ("Value of optional fields i {0}".format(optionalFields))
        log.info ("Value of optional sec level is {0}".format(optionalSecLevel))
        return defaultFields, mandatoryFields, mandatorySecLevel, optionalFields, optionalSecLevel

    '''
    returnFieldsDef - returns event definition separated by sections
    Parameters:
        data - event from audit.log file in a list of dictionary
        eventNumber - event number that needs to be queried
        module - Name of the module
        defaultFields - dictionary of default fields
        mandatoryFields - list is dictionary of mandatory fields
        mandatorySecLevel - list of dictionary containing 2nd level of mandatory fields
        optionalFields - list is dictionary of optional fields
        optionalSecLevel - list of dictionary containing 2nd level of optional fields
    Returns:
        Boolean - True if all field names match
    '''
    def validateFieldActualLog(self, data, eventNumber, module, defaultFields, mandatoryFields, manFieldSecLevel=None, optionalFields=None, optFieldSecLevel=None, method="Rest"):
        flag = True
        for items in defaultFields:
            log.info ("Default Value getting checked is - {0}".format(items))
            if items not in data:
                log.info (" Default value not matching with expected expected value is - {0}".format(items))
                flag = False
        for items in mandatoryFields:
            log.info ("Top Level Mandatory Field Default getting checked is - {0}".format(items))
            if items in data:
                if (isinstance ((data[items]), dict)):
                    for items1 in manFieldSecLevel:
                        tempStr = items1.split(":")
                        if tempStr[0] == items:
                            for items in data[items]:
                                log.info ("Second Level Mandatory Field Default getting checked is - {0}".format(items))
                                if (items not in tempStr and method is not 'REST'):
                                    log.info (" Second level Mandatory field not matching with expected expected value is - {0}".format(items))
                                    flag = False
            else:
                flag = False
                if (method == 'REST' and items == 'sessionid'):
                    flag = True
                log.info (" Top level Mandatory field not matching with expected expected value is - {0}".format(items))
        for items in optionalFields:
            log.info ("Top Level Optional Field Default getting checked is - {0}".format(items))
            if items in data:
                if (isinstance ((data[items]), dict)):
                    for items1 in optFieldSecLevel:
                        tempStr = items1.split(":")
                        if tempStr[0] == items:
                            for items in data[items]:
                                log.info ("Second Level Optional Field Default getting checked is - {0}".format(items))
                                if (items not in tempStr and method is not 'REST'):
                                    log.info (" Second level Optional field not matching with expected expected value is - {0}".format(items))
                                    flag = False
            else:
                flag = False
                if (method == 'REST' and items == "sessionid"):
                    flag = True
                log.info (" Top level Optional field not matching with expected expected value is - {0}".format(items))
        return flag

    '''
    validateData - validate data from audit.log with expected Result
    Parameters:
        data - event data from audit.log, based on eventID
        expectedResult - dictionary of expected Result to be validated
    Results:
        Boolean - True if data from audit.log matches with expectedResult
    '''

    def validateData(self, data, expectedResult):
        log.info (" Event from audit.log -- {0}".format(data))
        flag = True
        for items in data:
            if items == 'timestamp':
                flag = self.validateTimeStamp(data['timestamp'])
            else:
                if (isinstance(data[items], dict)):
                    for seclevel in data[items]:
                        tempLevel = items + ":" + seclevel
                        if (tempLevel in expectedResult.keys()):
                            tempValue = expectedResult[tempLevel]
                        else:
                            tempValue = expectedResult[seclevel]
                        if (seclevel == 'port' and data[items][seclevel] >= 30000 and data[items][seclevel] <= 65535):
                            log.info ("Matching port is an ephemeral port -- actual port is {0}".format(data[items][seclevel]))
                        else:
                            #log.info ('expected values - {0} -- actual value -- {1} - eventName - {2}'.format(tempValue, data[items][seclevel], seclevel))
                            if data[items][seclevel] == tempValue:
                                log.info ('Match Found expected values - {0} -- actual value -- {1} - eventName - {2}'.format(tempValue, data[items][seclevel], seclevel))
                            else:
                                log.info ('Mis-Match Found expected values - {0} -- actual value -- {1} - eventName - {2}'.format(tempValue, data[items][seclevel], seclevel))
                                flag = False
                else:
                    if (items == 'port' and data[items] >= 30000 and data[items] <= 65535):
                        log.info ("Matching port is an ephemeral port -- actual port is {0}".format(data[items]))
                    else:
                        #log.info ('expected values - {0} -- actual value -- {1} - eventName - {2}'.format(expectedResult[items.encode('utf-8')], data[items.encode('utf-8')], items))
                        if (data[items] == expectedResult[items]):
                            log.info ('Match Found expected values - {0} -- actual value -- {1} - eventName - {2}'.format(expectedResult[items.encode('utf-8')], data[items.encode('utf-8')], items))
                        else:
                            log.info ('Mis - Match Found expected values - {0} -- actual value -- {1} - eventName - {2}'.format(expectedResult[items.encode('utf-8')], data[items.encode('utf-8')], items))
                            flag = False
        return flag

    '''
    validateDate - validate date from audit.log and current date
    Parameters:
        actualDate - timestamp captured from audit.log for event
    Results:
        Boolean - True if difference of timestamp is < 30 seconds
    '''
    def validateTimeStamp(self, actualTime=None):
        try:
            date = actualTime[:10]
            hourMin = actualTime[11:16]
            shell = RemoteMachineShellConnection(self.host)
            try:
                currDate = shell.execute_command('date +"%Y-%m-%d"')
                currHourMin = shell.execute_command('date +"%H:%M"')
            finally:
                shell.disconnect()
            log.info (" Matching expected date - currDate {0}; actual Date - {1}".format(currDate[0][0], date))
            log.info (" Matching expected time - currDate {0} ; actual Date - {1}".format(currHourMin[0][0], hourMin))
            if ((date == currDate[0][0]) and (hourMin == currHourMin[0][0])):
                log.info ("Matching values found for timestamp")
                return True
            else:
                #Compare time and minutes, will fail if time is 56 mins or above
                if ((int((hourMin.split(":"))[0])) == (int((currHourMin.split(":"))[0]))) and ((int((hourMin.split(":"))[1])) < (int((currHourMin.split(":"))[1]) + 4)):
                       log.info ("Matching values found for timestamp")
                else:
                    log.info ("Mis-match in values for timestamp")
                    return False
        except:
            log.info ("Into Exception")
            return False


    '''
    validateEvents - external interface to validate event definition and value from audit.log
    Parameters:
        expectedResults - dictionary of keys as fields in audit.log and expected values for reach
    Returns:
        fieldVerification - Boolean - True if all matching fields have been found. 
        valueVerification - Boolean - True if data matches with expected Results
    '''
    def validateEvents(self, expectedResults):
        defaultField, mandatoryFields, mandatorySecLevel, optionalFields, optionalSecLevel = self.returnFieldsDef(self.eventDef, self.eventID)
        actualEvent = self.returnEvent(self.eventID)
        fieldVerification = self.validateFieldActualLog(actualEvent, self.eventID, 'ns_server', self.defaultFields, mandatoryFields, \
                                                    mandatorySecLevel, optionalFields, optionalSecLevel, self.method)
        expectedResults = dict(defaultField.items() + expectedResults.items())
        valueVerification = self.validateData(actualEvent, expectedResults)
        return fieldVerification, valueVerification


    def checkLastEvent(self):
        try:
            actualEvent = self.returnEvent(self.eventID)
            return self.validateTimeStamp(actualEvent['timestamp'])
        except:
            return False