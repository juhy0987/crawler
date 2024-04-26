import sys
import time
import atexit
import threading
import multiprocessing

from .ThreadMgr import ThreadMgr
from .ThreadMgr import thread

def process (processId, chiefMgrConn, managers, urlQ, writerQ):
  if not chiefMgrConn:
    raise BaseException
  
  configMgr = managers[0]
  judgementTreeMgr = managers[1]
  duplicationDBMgr = managers[2]
  
  qEmptyTimeoutCnt = 0
  config = configMgr.getConfig()
  threadMgr = ThreadMgr(config.MaxThread)
  sys.stderr = open(config.LogFilePath, "at")
  
  # debug
  # print("Process[{}] Initiated ".format(processId), file=sys.__stdout__)
  updateCnt = 0
  while qEmptyTimeoutCnt < config.qEmptyTimeoutLimit:
    # config control
    if chiefMgrConn.poll(0.1):
      data = chiefMgrConn.recv()
      try:
        data = data.split()
        match data[0]:
          case "C":
            match data[1]:
              case "U":
                config = configMgr.getConfig()
                
                # apply changed configuration
                threadMgr.setMaxThread(config.MaxThread)
              case _:
                pass
          case _:
            pass
      except Exception as e:
        print("[Process Insite] Error occured: {}".format(str(e)), file=sys.__stdout__)
    
    # debug
    # print("Process[{}] {} Threads Running".format(processId, len(threadMgr.threads)), file=sys.__stdout__)
    
    deadlist = []
    for id in threadMgr.threads.keys():
      if not threadMgr.isThreadAlive(id):
        deadlist.append(id)
    for id in deadlist:
      threadMgr.delThread(id)
      threadMgr.setUnusedNum(id)
    
    if len(threadMgr.threads) < config.MaxThread and not urlQ.empty():
      threadMgr.addThread(thread, (config, managers, urlQ, writerQ))
    
    if urlQ.empty() and not len(threadMgr.threads):
      qEmptyTimeoutCnt += 1
    else:
      qEmptyTimeoutCnt = 0
    
    time.sleep(1)
  
  # print("Process[{}] Finally Terminated ".format(processId), file=sys.__stdout__)
  

  