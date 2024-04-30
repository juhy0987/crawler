import sys
import time
import atexit
import threading
import multiprocessing
import signal

import selenium
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By

from Config import Config
from modules import SearchDriver

class CrawlerPIDMgr(multiprocessing.managers.Namespace):
  def __init__(self):
    self.pid = dict()
  
  def setPid(self, processId, pid):
    self.pid[processId] = pid
  
  def getPid(self):
    return self.pid

def process (processId, chiefMgrConn, managers, urlQ, writerQ):
  if not chiefMgrConn:
    raise BaseException
  
  qEmptyTimeoutCnt = 0
  config = managers[0].getConfig()
  sys.stderr = open(config.LogFilePath, "at")
  crawler = None
  
  # debug
  print("Process[{}] Initiated ".format(processId), file=sys.__stdout__)
  signal.signal(signal.SIGINT, sigIntHanlder)
  atexit.register(closeDriver, crawler)
  while qEmptyTimeoutCnt < config.qEmptyTimeoutLimit:
    # config control
    sys.stderr = config.applyLog(sys.stderr)
    if chiefMgrConn.poll(0.01):
      data = chiefMgrConn.recv()
      try:
        data = data.split()
        match data[0]:
          case "C":
            match data[1]:
              case "U":
                config = managers[0].getConfig()
                
                # apply changed configuration
              case _:
                pass
          case _:
            pass
      except Exception as e:
        print("[Process Insite] Error occured: {}".format(str(e)), file=sys.__stdout__)
    # debug
    # print("Process[{}] {} Threads Running".format(processId, len(threadMgr.threads)), file=sys.__stdout__)
    
    if urlQ.empty():
      qEmptyTimeoutCnt += 1
      time.sleep(1)
      continue
    qEmptyTimeoutCnt = 0
    url, depth = urlQ.get()
    closeDriver(crawler)
    crawler = SearchDriver()
    managers[3].setPid(processId, crawler.service.process.pid)
    wait = WebDriverWait(crawler, timeout=1)
    
    if managers[2].mutualCheck(url):
      continue
    
    try:
      crawler.get(url)
      crawler.implicitly_wait(3)
    except selenium.common.exceptions.WebDriverException as e:
      if "net::ERR_CONNECTION_TIMED_OUT" in e.msg:
        print("[Crawler Load] TIMED OUT: {}".format(url), file=sys.stderr)
        continue
      elif "invalid session id" in e.msg:
        print("[Crawler Load] Invalid session id: {}".format(url), file=sys.stderr)
        continue
      elif "net::ERR_NAME_NOT_RESOLVED" in e.msg:
        print("[Crawler Load] Name Not Resolved: {}".format(url), file=sys.stderr)
        continue
      elif "net::ERR_INTERNET_DISCONNECTED" in e.msg:
        urlQ.put((url, depth))
        continue
      else:
        print("[Crawler Load] Unhandled Error: {}'\n: {}".format(e.msg, url), file=sys.stderr)
        raise e
    except selenium.common.exceptions.InvalidSessionIdException as e:
      if "invalid session id" in e.msg:
        print("[Crawler Load] Invalid session id(Bot Detected): {}".format(url), file=sys.stderr)
        continue
      else:
        print("[Crawler Load] Unhandled Error: {}'\n: {}".format(e.msg, url), file=sys.stderr)
        raise e
    except Exception as e:
      print("[Crawler Load] Unhandled Error: {}'\n: {}".format(e, url), file=sys.stderr)
      raise e
  
    ############### Weights Calculation ################
    if url != crawler.current_url:
      if "warning.or.kr" in crawler.current_url:
        # 위해 사이트
        continue
      else:
        url  = crawler.current_url
      
    if depth > 0 or config.CheckZeroDepth:
      pass
    
    writerQ.put(url)
    if depth < config.MaxDepth:
      try:
        wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "a")))
        tag_a = crawler.find_elements(By.TAG_NAME, "a")
      except (selenium.common.exceptions.TimeoutException,
              selenium.common.exceptions.StaleElementReferenceException):
        print("[Crawler Running] Next Link Time Out: {}".format(url), file=sys.stderr)
        continue
        
      for tag in tag_a:
        try:
          link = tag.get_attribute('href')
          
          if link:
            sharp = link.find('#')
            if sharp > -1:
              link = link[:sharp]
            
            if len(link) > 1 and link[-1] == '/':
              link = link[:-1]
            
            if len(link) > 10 and link[:10] == "javascript":
              continue
            
            if not managers[2].lookup(link):
              urlQ.put((link, depth+1))
        except (selenium.common.exceptions.TimeoutException,
              selenium.common.exceptions.StaleElementReferenceException):
          continue
    ####################################################
  
def sigIntHanlder(signal, frame):
  print("Process Terminated", file=sys.__stdout__)
  sys.exit(0)

def closeDriver(driver):
  if driver:
    try:
      driver.close()
    except:
      pass
    try:
      driver.quit()
    except:
      pass