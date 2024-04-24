import time
import atexit
import threading
import multiprocessing

def processFailHanlder(q, curURL=("", 0)):
  q.put(curURL)

def URLFailHandler(sURL):
  # logging
  pass

def process (id, chiefMgrConn, config, q):
  if not chiefMgrConn:
    raise BaseException
  
  # 0: main(writer) process, 1: judgement DB, 2: duplication check DB
  lConn = [None, None, None]
  
  connUpdater = threading.Thread(name="process"+str(id)+"_judgeDBUpdater",
                                        target=updater,
                                        args=(lConn, chiefMgrConn))
  qEmptyTimeoutCnt = 0
  if config.acquire(block=False):
    qEmptyTimeoutLimit = config.qEmptyTimeoutLimit
    config.release()
  while qEmptyTimeoutCnt < qEmptyTimeoutLimit:
    
    
    if q.empty():
      qEmptyTimeoutCnt += 1
      time.sleep(1)
    else:
      qEmptyTimeoutCnt = 0

def updater(conn):
  with condition:
    while True:
      condition.wait()
      
  